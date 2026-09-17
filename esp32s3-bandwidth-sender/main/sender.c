#include "sender.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/select.h>
#include <unistd.h>

#include "esp_event.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_rom_sys.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "lwip/inet.h"
#include "lwip/tcp.h"
#include "nvs_flash.h"

static const char *TAG = "sender";

#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT BIT1
#define WIFI_MAX_RETRY 10
#define FRAME_HEADER_BYTES 12
#define FRAME_CRC_BYTES 2
#define FRAME_BYTES (FRAME_HEADER_BYTES + CONFIG_BANDWIDTH_PAYLOAD_BYTES + FRAME_CRC_BYTES)
#define FRAME_INTERVAL_US (1000000 / CONFIG_BANDWIDTH_FPS)
#define TELEMETRY_WINDOW_US 50000
#define TELEMETRY_OFFSET (FRAME_HEADER_BYTES)
#define TELEMETRY_MAGIC 0x314c4554U
#define TELEMETRY_VERSION 2U
#define EXTENDED_TELEMETRY_BYTES 52U

#ifndef CONFIG_BANDWIDTH_DIAG_STATIC_PAYLOAD
#define CONFIG_BANDWIDTH_DIAG_STATIC_PAYLOAD 0
#endif

#ifndef CONFIG_BANDWIDTH_DIAG_DISABLE_CRC
#define CONFIG_BANDWIDTH_DIAG_DISABLE_CRC 0
#endif

#ifndef CONFIG_BANDWIDTH_LOG_DROPPED_FRAMES
#define CONFIG_BANDWIDTH_LOG_DROPPED_FRAMES 0
#endif

#ifndef CONFIG_BANDWIDTH_UDP_BLOCKING_FAST_SEND
#define CONFIG_BANDWIDTH_UDP_BLOCKING_FAST_SEND 0
#endif

#ifndef CONFIG_BANDWIDTH_PRECISE_PACING
#define CONFIG_BANDWIDTH_PRECISE_PACING 0
#endif

#ifndef CONFIG_BANDWIDTH_DROP_LATE_FRAMES
#define CONFIG_BANDWIDTH_DROP_LATE_FRAMES 0
#endif

#ifndef CONFIG_BANDWIDTH_MAX_LATE_FRAMES
#define CONFIG_BANDWIDTH_MAX_LATE_FRAMES 1
#endif

#ifndef CONFIG_BANDWIDTH_TCP_BLOCKING_SEND
#define CONFIG_BANDWIDTH_TCP_BLOCKING_SEND 0
#endif

#ifndef CONFIG_BANDWIDTH_TCP_NODELAY
#define CONFIG_BANDWIDTH_TCP_NODELAY 0
#endif

#ifndef CONFIG_BANDWIDTH_TCP_BATCH_FRAMES
#define CONFIG_BANDWIDTH_TCP_BATCH_FRAMES 1
#endif

#ifndef CONFIG_BANDWIDTH_LOG_STATS
#define CONFIG_BANDWIDTH_LOG_STATS 0
#endif

#ifndef CONFIG_BANDWIDTH_EXTENDED_TELEMETRY
#define CONFIG_BANDWIDTH_EXTENDED_TELEMETRY 0
#endif

#ifndef CONFIG_BANDWIDTH_UNLIMITED_YIELD_EVERY_N_FRAMES
#define CONFIG_BANDWIDTH_UNLIMITED_YIELD_EVERY_N_FRAMES 0
#endif

#ifndef CONFIG_BANDWIDTH_UNLIMITED_DELAY_EVERY_N_FRAMES
#define CONFIG_BANDWIDTH_UNLIMITED_DELAY_EVERY_N_FRAMES 0
#endif

static EventGroupHandle_t wifi_event_group;
static int wifi_retry_count;
static bool wall_clock_time_valid;
static uint64_t diagnostic_backpressure_events;
static uint64_t diagnostic_fatal_send_errors;
static uint64_t diagnostic_eagain_events;
static uint64_t diagnostic_enobufs_events;
static uint64_t diagnostic_enomem_events;
static uint64_t diagnostic_eintr_events;
static uint64_t diagnostic_partial_send_events;
static int32_t diagnostic_last_errno;

typedef enum {
    SEND_FRAME_OK,
    SEND_FRAME_DROPPED,
    SEND_FRAME_FATAL,
} send_frame_result_t;

typedef struct {
    uint64_t send_ok_ts_us;
    uint32_t seq;
} send_success_record_t;

static void write_u32_le(uint8_t *dst, uint32_t value)
{
    dst[0] = (uint8_t)(value & 0xff);
    dst[1] = (uint8_t)((value >> 8) & 0xff);
    dst[2] = (uint8_t)((value >> 16) & 0xff);
    dst[3] = (uint8_t)((value >> 24) & 0xff);
}

static void write_u64_le(uint8_t *dst, uint64_t value)
{
    for (size_t i = 0; i < 8; ++i) {
        dst[i] = (uint8_t)((value >> (i * 8)) & 0xff);
    }
}

static uint16_t crc16_ccitt_false(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xffff;

    for (size_t i = 0; i < len; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (int bit = 0; bit < 8; ++bit) {
            if ((crc & 0x8000) != 0) {
                crc = (uint16_t)((crc << 1) ^ 0x1021);
            } else {
                crc <<= 1;
            }
        }
    }

    return crc;
}

static uint64_t current_send_timestamp_us(void)
{
    if (wall_clock_time_valid) {
        struct timeval now;
        gettimeofday(&now, NULL);
        return (uint64_t)now.tv_sec * 1000000ULL + (uint64_t)now.tv_usec;
    }

    return (uint64_t)esp_timer_get_time();
}

static send_success_record_t *send_success_records;
static size_t send_success_record_count;
static uint64_t send_success_record_overflow;

static void record_send_success(uint32_t seq)
{
#if CONFIG_BANDWIDTH_RECORD_SEND_SUCCESSES
    if (send_success_records != NULL && send_success_record_count < CONFIG_BANDWIDTH_SEND_RECORD_CAPACITY) {
        send_success_records[send_success_record_count++] = (send_success_record_t){
            .send_ok_ts_us = current_send_timestamp_us(),
            .seq = seq,
        };
    } else {
        send_success_record_overflow++;
    }
#else
    (void)seq;
#endif
}

static void export_send_success_records(uint64_t send_fail_events, uint64_t fatal_send_errors)
{
#if CONFIG_BANDWIDTH_RECORD_SEND_SUCCESSES
    printf("SEND_SUCCESS_EXPORT_BEGIN count=%u overflow=%" PRIu64 " send_fail_events=%" PRIu64
           " fatal_send_errors=%" PRIu64 "\n",
           (unsigned)send_success_record_count,
           send_success_record_overflow,
           send_fail_events,
           fatal_send_errors);
    printf("send_ok_ts_us,seq\n");
    for (size_t i = 0; i < send_success_record_count; ++i) {
        printf("%" PRIu64 ",%" PRIu32 "\n",
               send_success_records[i].send_ok_ts_us,
               send_success_records[i].seq);
    }
    printf("SEND_SUCCESS_EXPORT_END\n");
#else
    (void)send_fail_events;
    (void)fatal_send_errors;
#endif
}

static void wait_until_us(int64_t target_us)
{
    while (true) {
        const int64_t now_us = esp_timer_get_time();
        const int64_t remaining_us = target_us - now_us;
        if (remaining_us <= 0) {
            return;
        }

#if CONFIG_BANDWIDTH_PRECISE_PACING
        if (remaining_us <= 2000) {
            esp_rom_delay_us((uint32_t)remaining_us);
            return;
        }
#endif

        const int64_t sleep_ms = remaining_us / 1000;
        vTaskDelay(pdMS_TO_TICKS(sleep_ms > 0 ? sleep_ms : 1));
    }
}

static bool wait_for_socket_writable(int sock, int timeout_ms)
{
    fd_set writefds;
    FD_ZERO(&writefds);
    FD_SET(sock, &writefds);

    struct timeval timeout = {
        .tv_sec = timeout_ms / 1000,
        .tv_usec = (timeout_ms % 1000) * 1000,
    };

    while (true) {
        const int ret = select(sock + 1, NULL, &writefds, NULL, timeout_ms >= 0 ? &timeout : NULL);
        if (ret > 0) {
            return FD_ISSET(sock, &writefds);
        }
        if (ret == 0) {
            return false;
        }
        if (errno != EINTR) {
            ESP_LOGW(TAG, "select() while waiting for UDP socket writable failed: errno %d", errno);
            return false;
        }

        FD_ZERO(&writefds);
        FD_SET(sock, &writefds);
        timeout.tv_sec = timeout_ms / 1000;
        timeout.tv_usec = (timeout_ms % 1000) * 1000;
    }
}

static void fill_frame_payload(uint8_t *frame)
{
    for (size_t i = 0; i < CONFIG_BANDWIDTH_PAYLOAD_BYTES; ++i) {
        frame[FRAME_HEADER_BYTES + i] = (uint8_t)(i & 0xff);
    }
}

static void fill_frame(uint8_t *frame, uint32_t seq, uint32_t telemetry_window,
                       uint32_t telemetry_offered, uint32_t telemetry_sent,
                       uint32_t telemetry_dropped)
{
#if !CONFIG_BANDWIDTH_DIAG_STATIC_PAYLOAD
    for (size_t i = 0; i < CONFIG_BANDWIDTH_PAYLOAD_BYTES; ++i) {
        frame[FRAME_HEADER_BYTES + i] = (uint8_t)((seq + i) & 0xff);
    }
#endif

#if CONFIG_BANDWIDTH_50MS_TELEMETRY || CONFIG_BANDWIDTH_EXTENDED_TELEMETRY
    if (CONFIG_BANDWIDTH_PAYLOAD_BYTES >= 20) {
        write_u32_le(frame + TELEMETRY_OFFSET, TELEMETRY_MAGIC);
#if CONFIG_BANDWIDTH_50MS_TELEMETRY
        write_u32_le(frame + TELEMETRY_OFFSET + 4, telemetry_window);
        write_u32_le(frame + TELEMETRY_OFFSET + 8, telemetry_offered);
        write_u32_le(frame + TELEMETRY_OFFSET + 12, telemetry_sent);
        write_u32_le(frame + TELEMETRY_OFFSET + 16, telemetry_dropped);
#else
        write_u32_le(frame + TELEMETRY_OFFSET + 4, 0);
        write_u32_le(frame + TELEMETRY_OFFSET + 8, 0);
        write_u32_le(frame + TELEMETRY_OFFSET + 12, 0);
        write_u32_le(frame + TELEMETRY_OFFSET + 16, 0);
#endif
#if CONFIG_BANDWIDTH_EXTENDED_TELEMETRY
        if (CONFIG_BANDWIDTH_PAYLOAD_BYTES >= EXTENDED_TELEMETRY_BYTES) {
            // Version 2 extends the original 20-byte snapshot without changing
            // FRAME_BYTES: these bytes replace ordinary payload bytes.
            write_u32_le(frame + TELEMETRY_OFFSET + 20, TELEMETRY_VERSION);
            write_u32_le(frame + TELEMETRY_OFFSET + 24, (uint32_t)diagnostic_backpressure_events);
            write_u32_le(frame + TELEMETRY_OFFSET + 28, (uint32_t)diagnostic_fatal_send_errors);
            write_u32_le(frame + TELEMETRY_OFFSET + 32, (uint32_t)diagnostic_eagain_events);
            write_u32_le(frame + TELEMETRY_OFFSET + 36, (uint32_t)diagnostic_enobufs_events);
            write_u32_le(frame + TELEMETRY_OFFSET + 40, (uint32_t)diagnostic_enomem_events);
            write_u32_le(frame + TELEMETRY_OFFSET + 44, (uint32_t)diagnostic_last_errno);
            write_u32_le(frame + TELEMETRY_OFFSET + 48, (uint32_t)(esp_timer_get_time() / 1000));
        }
#endif
    }
#endif

    // Stamp after payload/telemetry preparation, immediately before CRC and send.
    // This is a pre-send socket-boundary timestamp, not an 802.11 airtime timestamp.
    const uint64_t timestamp_us = current_send_timestamp_us();
    write_u32_le(frame, seq);
    write_u64_le(frame + 4, timestamp_us);

#if CONFIG_BANDWIDTH_DIAG_DISABLE_CRC
    const uint16_t crc = 0;
#else
    const uint16_t crc = crc16_ccitt_false(frame, FRAME_HEADER_BYTES + CONFIG_BANDWIDTH_PAYLOAD_BYTES);
#endif
    frame[FRAME_HEADER_BYTES + CONFIG_BANDWIDTH_PAYLOAD_BYTES] = (uint8_t)(crc & 0xff);
    frame[FRAME_HEADER_BYTES + CONFIG_BANDWIDTH_PAYLOAD_BYTES + 1] = (uint8_t)((crc >> 8) & 0xff);
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        if (wifi_retry_count < WIFI_MAX_RETRY) {
            wifi_retry_count++;
            ESP_LOGW(TAG, "WiFi disconnected, retrying (%d/%d)", wifi_retry_count, WIFI_MAX_RETRY);
            esp_wifi_connect();
        } else {
            xEventGroupSetBits(wifi_event_group, WIFI_FAIL_BIT);
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *event = (const ip_event_got_ip_t *)event_data;
        wifi_retry_count = 0;
        ESP_LOGI(TAG, "WiFi connected, got IP: " IPSTR, IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static void log_ap_info(void)
{
    wifi_ap_record_t ap_info = {0};
    const esp_err_t ret = esp_wifi_sta_get_ap_info(&ap_info);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Unable to read AP info: %s", esp_err_to_name(ret));
        return;
    }

    uint8_t primary = 0;
    wifi_second_chan_t second = WIFI_SECOND_CHAN_NONE;
    if (esp_wifi_get_channel(&primary, &second) != ESP_OK) {
        primary = ap_info.primary;
        second = WIFI_SECOND_CHAN_NONE;
    }

    ESP_LOGI(TAG,
             "AP info: ssid=%s, rssi=%d dBm, channel=%u, second=%d, authmode=%d, phy_11b=%d, phy_11g=%d, phy_11n=%d",
             (const char *)ap_info.ssid,
             ap_info.rssi,
             primary,
             second,
             ap_info.authmode,
             ap_info.phy_11b,
             ap_info.phy_11g,
             ap_info.phy_11n);
}

static void log_link_diagnostics(void)
{
    wifi_ap_record_t ap_info = {0};
    uint8_t primary = 0;
    wifi_second_chan_t second = WIFI_SECOND_CHAN_NONE;
    const esp_err_t ap_ret = esp_wifi_sta_get_ap_info(&ap_info);
    const esp_err_t channel_ret = esp_wifi_get_channel(&primary, &second);
    ESP_LOGI(TAG,
             "link rssi=%d dBm channel=%u second=%d free_heap=%u min_heap=%u uptime_ms=%" PRIu32,
             ap_ret == ESP_OK ? ap_info.rssi : 0,
             channel_ret == ESP_OK ? primary : 0,
             channel_ret == ESP_OK ? second : WIFI_SECOND_CHAN_NONE,
             (unsigned)esp_get_free_heap_size(),
             (unsigned)esp_get_minimum_free_heap_size(),
             (uint32_t)(esp_timer_get_time() / 1000));
}

static esp_err_t wifi_init_sta(void)
{
    esp_err_t ret;

    wifi_event_group = xEventGroupCreate();
    if (wifi_event_group == NULL) {
        return ESP_ERR_NO_MEM;
    }

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    const wifi_init_config_t init_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_config));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event_handler, NULL, NULL));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = CONFIG_BANDWIDTH_WIFI_SSID,
            .password = CONFIG_BANDWIDTH_WIFI_PASSWORD,
            .threshold.authmode = WIFI_AUTH_WPA2_PSK,
        },
    };

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));

    ESP_ERROR_CHECK(esp_wifi_start());

    // These settings require an initialized/running Wi-Fi driver. Applying
    // them before esp_wifi_start() can return ESP_ERR_INVALID_ARG and leave
    // the station on the default protocol or channel width.
#if CONFIG_BANDWIDTH_WIFI_11N_ONLY
    ret = esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11N);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "WiFi protocol requested: 802.11n only");
    } else {
        ESP_LOGW(TAG, "Unable to set WiFi protocol to 802.11n only: %s", esp_err_to_name(ret));
    }
#elif CONFIG_BANDWIDTH_WIFI_11GN_ONLY
    ret = esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11G | WIFI_PROTOCOL_11N);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "WiFi protocol requested: 802.11g/n; 802.11b disabled");
    } else {
        ESP_LOGW(TAG, "Unable to set WiFi protocol to 802.11g/n: %s", esp_err_to_name(ret));
    }
#endif

#if CONFIG_BANDWIDTH_WIFI_HT40
    ret = esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW40);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "WiFi bandwidth requested: HT40");
    } else {
        ESP_LOGW(TAG, "Unable to set WiFi HT40 bandwidth: %s", esp_err_to_name(ret));
    }
#endif

#if CONFIG_BANDWIDTH_WIFI_PS_NONE
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_LOGI(TAG, "WiFi power save disabled for throughput diagnostics");
#else
    ESP_LOGI(TAG, "WiFi power save uses ESP-IDF default");
#endif

    ESP_LOGI(TAG, "Connecting to WiFi SSID: %s", CONFIG_BANDWIDTH_WIFI_SSID);

    const EventBits_t bits = xEventGroupWaitBits(
        wifi_event_group,
        WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
        pdFALSE,
        pdFALSE,
        portMAX_DELAY);

    if (bits & WIFI_CONNECTED_BIT) {
        log_ap_info();
#if CONFIG_BANDWIDTH_WIFI_11N_ONLY || CONFIG_BANDWIDTH_WIFI_11GN_ONLY
        uint8_t actual_protocol = 0;
        if (esp_wifi_get_protocol(WIFI_IF_STA, &actual_protocol) == ESP_OK) {
            ESP_LOGI(TAG, "WiFi active protocol mask: 0x%02x", actual_protocol);
        }
#endif
#if CONFIG_BANDWIDTH_WIFI_HT40
        wifi_bandwidth_t actual_bandwidth = WIFI_BW20;
        if (esp_wifi_get_bandwidth(WIFI_IF_STA, &actual_bandwidth) == ESP_OK) {
            ESP_LOGI(TAG, "WiFi active bandwidth: %s", actual_bandwidth == WIFI_BW40 ? "HT40" : "HT20");
        }
#endif
        return ESP_OK;
    }

    ESP_LOGE(TAG, "Failed to connect to WiFi SSID: %s", CONFIG_BANDWIDTH_WIFI_SSID);
    return ESP_FAIL;
}

static void sync_wall_clock_time(void)
{
#if CONFIG_BANDWIDTH_SNTP_ENABLE
    bool sntp_started = false;

    while (true) {
        if (!sntp_started) {
            esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG(CONFIG_BANDWIDTH_SNTP_SERVER);
            config.start = true;

            ESP_LOGI(TAG, "Starting SNTP synchronization with %s before streaming", CONFIG_BANDWIDTH_SNTP_SERVER);
            esp_err_t init_ret = esp_netif_sntp_init(&config);
            if (init_ret == ESP_OK || init_ret == ESP_ERR_INVALID_STATE) {
                sntp_started = true;
            } else {
                ESP_LOGW(TAG, "SNTP init failed (%s)", esp_err_to_name(init_ret));
#if CONFIG_BANDWIDTH_REQUIRE_SNTP
                ESP_LOGW(TAG, "SNTP is required for this firmware; retrying in 5 seconds");
                vTaskDelay(pdMS_TO_TICKS(5000));
                continue;
#else
                ESP_LOGW(TAG, "Using monotonic timestamps");
                wall_clock_time_valid = false;
                return;
#endif
            }
        }

        ESP_LOGI(TAG, "Waiting up to %d ms for epoch-aligned SNTP time", CONFIG_BANDWIDTH_SNTP_SYNC_TIMEOUT_MS);
        const esp_err_t sync_ret = esp_netif_sntp_sync_wait(pdMS_TO_TICKS(CONFIG_BANDWIDTH_SNTP_SYNC_TIMEOUT_MS));
        if (sync_ret == ESP_OK) {
            struct timeval now;
            gettimeofday(&now, NULL);
            if (now.tv_sec > 1600000000L) {
                wall_clock_time_valid = true;
                ESP_LOGI(TAG,
                         "SNTP synchronized with %s; frame timestamps are Unix epoch microseconds",
                         CONFIG_BANDWIDTH_SNTP_SERVER);
                return;
            }
        }

        wall_clock_time_valid = false;
#if CONFIG_BANDWIDTH_REQUIRE_SNTP
        ESP_LOGW(TAG,
                 "SNTP sync did not complete within %d ms; waiting before streaming",
                 CONFIG_BANDWIDTH_SNTP_SYNC_TIMEOUT_MS);
        vTaskDelay(pdMS_TO_TICKS(5000));
#else
        ESP_LOGW(TAG,
                 "SNTP sync did not complete within %d ms; using monotonic timestamps",
                 CONFIG_BANDWIDTH_SNTP_SYNC_TIMEOUT_MS);
        return;
#endif
    }
#else
    wall_clock_time_valid = false;
    ESP_LOGI(TAG, "SNTP disabled; using monotonic timestamps");
#endif
}

static int connect_tcp_server(void)
{
    struct sockaddr_in dest_addr = {
        .sin_family = AF_INET,
        .sin_port = htons(CONFIG_BANDWIDTH_SERVER_PORT),
    };

    if (inet_pton(AF_INET, CONFIG_BANDWIDTH_SERVER_IP, &dest_addr.sin_addr) != 1) {
        ESP_LOGE(TAG, "Invalid server IP: %s", CONFIG_BANDWIDTH_SERVER_IP);
        return -1;
    }

    const int sock = socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(TAG, "Unable to create socket: errno %d", errno);
        return -1;
    }

    ESP_LOGI(TAG, "Connecting to TCP server %s:%d", CONFIG_BANDWIDTH_SERVER_IP, CONFIG_BANDWIDTH_SERVER_PORT);
    if (connect(sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr)) != 0) {
        ESP_LOGE(TAG, "Socket connect failed: errno %d", errno);
        shutdown(sock, SHUT_RDWR);
        close(sock);
        return -1;
    }

    ESP_LOGI(TAG, "TCP connected");

#if CONFIG_BANDWIDTH_TCP_NODELAY
    const int one = 1;
    if (setsockopt(sock, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one)) != 0) {
        ESP_LOGW(TAG, "Failed to set TCP_NODELAY: errno %d", errno);
    } else {
        ESP_LOGI(TAG, "TCP_NODELAY enabled");
    }
#endif

    if (CONFIG_BANDWIDTH_SOCKET_SNDBUF > 0) {
        const int send_buffer_bytes = CONFIG_BANDWIDTH_SOCKET_SNDBUF;
        if (setsockopt(sock, SOL_SOCKET, SO_SNDBUF, &send_buffer_bytes, sizeof(send_buffer_bytes)) != 0) {
            ESP_LOGW(TAG, "Failed to set SO_SNDBUF=%d: errno %d", send_buffer_bytes, errno);
        }
    }

#if !CONFIG_BANDWIDTH_TCP_BLOCKING_SEND
    const int flags = fcntl(sock, F_GETFL, 0);
    if (flags >= 0 && fcntl(sock, F_SETFL, flags | O_NONBLOCK) != 0) {
        ESP_LOGW(TAG, "Failed to set socket non-blocking: errno %d", errno);
    }
#else
    ESP_LOGI(TAG, "TCP socket uses blocking send");
#endif

    return sock;
}

static int connect_udp_receiver(void)
{
    struct sockaddr_in dest_addr = {
        .sin_family = AF_INET,
        .sin_port = htons(CONFIG_BANDWIDTH_SERVER_PORT),
    };

    if (inet_pton(AF_INET, CONFIG_BANDWIDTH_SERVER_IP, &dest_addr.sin_addr) != 1) {
        ESP_LOGE(TAG, "Invalid receiver IP: %s", CONFIG_BANDWIDTH_SERVER_IP);
        return -1;
    }

    const int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(TAG, "Unable to create UDP socket: errno %d", errno);
        return -1;
    }

    if (CONFIG_BANDWIDTH_SOCKET_SNDBUF > 0) {
        const int send_buffer_bytes = CONFIG_BANDWIDTH_SOCKET_SNDBUF;
        if (setsockopt(sock, SOL_SOCKET, SO_SNDBUF, &send_buffer_bytes, sizeof(send_buffer_bytes)) != 0) {
            ESP_LOGW(TAG, "Failed to set UDP SO_SNDBUF=%d: errno %d", send_buffer_bytes, errno);
        }
    }

    if (connect(sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr)) != 0) {
        ESP_LOGE(TAG, "UDP connect failed: errno %d", errno);
        close(sock);
        return -1;
    }

#if !CONFIG_BANDWIDTH_UDP_BLOCKING_FAST_SEND
    const int flags = fcntl(sock, F_GETFL, 0);
    if (flags >= 0 && fcntl(sock, F_SETFL, flags | O_NONBLOCK) != 0) {
        ESP_LOGW(TAG, "Failed to set UDP socket non-blocking: errno %d", errno);
    }
#endif

    ESP_LOGI(TAG, "UDP target ready: %s:%d", CONFIG_BANDWIDTH_SERVER_IP, CONFIG_BANDWIDTH_SERVER_PORT);
    return sock;
}

static send_frame_result_t send_frame_blocking_udp(int sock, const uint8_t *frame, size_t frame_len,
                                                   uint64_t *send_fail_events)
{
    while (true) {
        const ssize_t sent = send(sock, frame, frame_len, 0);
        if (sent == (ssize_t)frame_len) {
            return SEND_FRAME_OK;
        }

        if (sent < 0 && errno == EINTR) {
            diagnostic_backpressure_events++;
            (*send_fail_events)++;
            diagnostic_eintr_events++;
            diagnostic_last_errno = EINTR;
            continue;
        }

        if (sent < 0 && (errno == ENOBUFS || errno == ENOMEM || errno == EAGAIN || errno == EWOULDBLOCK)) {
            diagnostic_backpressure_events++;
            (*send_fail_events)++;
            diagnostic_last_errno = errno;
            if (errno == ENOBUFS) diagnostic_enobufs_events++;
            if (errno == ENOMEM) diagnostic_enomem_events++;
            if (errno == EAGAIN || errno == EWOULDBLOCK) diagnostic_eagain_events++;
            (void)wait_for_socket_writable(sock, 25);
            continue;
        }

        if (sent >= 0 && sent != (ssize_t)frame_len) {
            diagnostic_partial_send_events++;
            diagnostic_last_errno = 0;
            ESP_LOGE(TAG, "blocking UDP send returned partial datagram: %d/%u bytes", (int)sent, (unsigned)frame_len);
            return SEND_FRAME_FATAL;
        }

        ESP_LOGE(TAG,
                 "blocking UDP send failed after %d/%u bytes: errno %d",
                 sent > 0 ? (int)sent : 0,
                 (unsigned)frame_len,
                 errno);
        diagnostic_last_errno = errno;
        return SEND_FRAME_FATAL;
    }
}

static send_frame_result_t send_frame_nonblocking_udp(int sock, const uint8_t *frame, size_t frame_len,
                                                      uint64_t *send_fail_events)
{
    while (true) {
        const ssize_t sent = send(sock, frame, frame_len, MSG_DONTWAIT);
        if (sent == (ssize_t)frame_len) {
            return SEND_FRAME_OK;
        }
        if (sent < 0 && errno == EINTR) {
            diagnostic_eintr_events++;
            diagnostic_last_errno = EINTR;
            diagnostic_backpressure_events++;
            (*send_fail_events)++;
            taskYIELD();
            continue;
        }
        if (sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == ENOBUFS || errno == ENOMEM)) {
            diagnostic_backpressure_events++;
            diagnostic_last_errno = errno;
            if (errno == ENOBUFS) diagnostic_enobufs_events++;
            if (errno == ENOMEM) diagnostic_enomem_events++;
            if (errno == EAGAIN || errno == EWOULDBLOCK) diagnostic_eagain_events++;
            (*send_fail_events)++;
            taskYIELD();
            continue;
        }
        ESP_LOGE(TAG, "fatal nonblocking UDP send failure: sent=%d/%u errno=%d",
                 (int)sent, (unsigned)frame_len, errno);
        diagnostic_last_errno = errno;
        return SEND_FRAME_FATAL;
    }
}

static send_frame_result_t send_frame_blocking_stream(int sock, const uint8_t *frame, size_t frame_len)
{
    size_t sent_total = 0;

    while (sent_total < frame_len) {
        const ssize_t sent = send(sock, frame + sent_total, frame_len - sent_total, 0);
        if (sent > 0) {
            sent_total += (size_t)sent;
            continue;
        }

        if (sent < 0 && errno == EINTR) {
            continue;
        }

        ESP_LOGE(TAG, "blocking TCP send failed after %u/%u bytes: errno %d",
                 (unsigned)sent_total,
                 (unsigned)frame_len,
                 errno);
        return SEND_FRAME_FATAL;
    }

    return SEND_FRAME_OK;
}

static send_frame_result_t send_frame_with_timeout(int sock, const uint8_t *frame, size_t frame_len)
{
    size_t sent_total = 0;
    const int64_t deadline_us = esp_timer_get_time() + (int64_t)CONFIG_BANDWIDTH_SEND_TIMEOUT_MS * 1000;

    while (sent_total < frame_len) {
        const ssize_t sent = send(sock, frame + sent_total, frame_len - sent_total, MSG_DONTWAIT);
        if (sent > 0) {
            sent_total += (size_t)sent;
            continue;
        }

        if (sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) {
            if (esp_timer_get_time() >= deadline_us) {
                return sent_total == 0 ? SEND_FRAME_DROPPED : SEND_FRAME_FATAL;
            }
            vTaskDelay(pdMS_TO_TICKS(1));
            continue;
        }

#if CONFIG_BANDWIDTH_TRANSPORT_UDP
        if (sent < 0 && sent_total == 0 && (errno == ENOBUFS || errno == ENOMEM)) {
            return SEND_FRAME_DROPPED;
        }
#endif

        ESP_LOGE(TAG, "send failed after %u/%u bytes: errno %d",
                 (unsigned)sent_total,
                 (unsigned)frame_len,
                 errno);
        return SEND_FRAME_FATAL;
    }

    return SEND_FRAME_OK;
}

static void sender_task(void *arg)
{
    (void)arg;
    ESP_LOGI(TAG, "Sender module initialized");

    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    if (wifi_init_sta() != ESP_OK) {
        while (true) {
            ESP_LOGE(TAG, "WiFi setup failed; reset the board or check SSID/password/hotspot");
            vTaskDelay(pdMS_TO_TICKS(2000));
        }
    }

    sync_wall_clock_time();

    const size_t tx_batch_frames =
#if CONFIG_BANDWIDTH_TRANSPORT_TCP
        CONFIG_BANDWIDTH_TCP_BATCH_FRAMES;
#else
        1;
#endif
    const size_t tx_buffer_bytes = FRAME_BYTES * tx_batch_frames;
    uint8_t *frame = (uint8_t *)malloc(tx_buffer_bytes);
    if (frame == NULL) {
        ESP_LOGE(TAG, "Unable to allocate %u-byte TX buffer", (unsigned)tx_buffer_bytes);
        vTaskDelete(NULL);
        return;
    }
    for (size_t batch_index = 0; batch_index < tx_batch_frames; ++batch_index) {
        fill_frame_payload(frame + batch_index * FRAME_BYTES);
    }

#if CONFIG_BANDWIDTH_RECORD_SEND_SUCCESSES
    const size_t send_record_bytes = (size_t)CONFIG_BANDWIDTH_SEND_RECORD_CAPACITY * sizeof(send_success_record_t);
    send_success_records = heap_caps_malloc(send_record_bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (send_success_records == NULL) {
        send_success_records = malloc(send_record_bytes);
    }
    if (send_success_records == NULL) {
        ESP_LOGW(TAG, "Unable to allocate %u bytes for send-success records; recording disabled",
                 (unsigned)send_record_bytes);
    } else {
        ESP_LOGI(TAG, "Recording up to %d successful UDP sends (%u bytes)",
                 CONFIG_BANDWIDTH_SEND_RECORD_CAPACITY, (unsigned)send_record_bytes);
    }
#endif

    uint32_t seq = 0;
    uint32_t sent_frames = 0;
    uint32_t dropped_frames = 0;
    uint64_t send_success_count = 0;
    uint64_t send_fail_events = 0;
    uint64_t fatal_send_errors = 0;
    uint32_t telemetry_window = 0;
    uint32_t telemetry_offered = 0;
    uint32_t telemetry_sent = 0;
    uint32_t telemetry_dropped = 0;
    int64_t telemetry_start_us = esp_timer_get_time();
    int64_t stats_start_us = esp_timer_get_time();
    int64_t next_frame_us = stats_start_us;
    int64_t test_start_us = 0;
    bool test_finished = false;

    ESP_LOGI(TAG,
             "Phase 5 calibrated sender: transport=%s, payload=%d bytes, frame=%u bytes, batch=%u, mode=%s, fps=%d, timeout=%d ms, timestamp=%s, precise_pacing=%d",
#if CONFIG_BANDWIDTH_TRANSPORT_UDP
             "udp",
#else
             "tcp",
#endif
             CONFIG_BANDWIDTH_PAYLOAD_BYTES,
             (unsigned)FRAME_BYTES,
             (unsigned)tx_batch_frames,
#if CONFIG_BANDWIDTH_UNLIMITED_SEND
             "unlimited",
#else
             "paced",
#endif
             CONFIG_BANDWIDTH_FPS,
             CONFIG_BANDWIDTH_SEND_TIMEOUT_MS,
             wall_clock_time_valid ? "epoch_us" : "monotonic_us",
             CONFIG_BANDWIDTH_PRECISE_PACING);

#if CONFIG_BANDWIDTH_DIAG_STATIC_PAYLOAD || CONFIG_BANDWIDTH_DIAG_DISABLE_CRC
    ESP_LOGW(TAG,
             "Diagnostic sender shortcuts enabled: static_payload=%d, crc_disabled=%d",
             CONFIG_BANDWIDTH_DIAG_STATIC_PAYLOAD,
             CONFIG_BANDWIDTH_DIAG_DISABLE_CRC);
#endif

    while (true) {
#if CONFIG_BANDWIDTH_TRANSPORT_UDP
        int sock = connect_udp_receiver();
#else
        int sock = connect_tcp_server();
#endif
        if (sock < 0) {
            vTaskDelay(pdMS_TO_TICKS(2000));
            continue;
        }
        if (test_start_us == 0) {
            test_start_us = esp_timer_get_time();
        }
        next_frame_us = esp_timer_get_time();
        telemetry_start_us = next_frame_us;
        telemetry_window = 0;
        telemetry_offered = 0;
        telemetry_sent = 0;
        telemetry_dropped = 0;

        while (true) {
#if CONFIG_BANDWIDTH_TEST_DURATION_S > 0
            if (test_start_us != 0 &&
                esp_timer_get_time() - test_start_us >= (int64_t)CONFIG_BANDWIDTH_TEST_DURATION_S * 1000000LL) {
                test_finished = true;
                break;
            }
#endif
#if !CONFIG_BANDWIDTH_UNLIMITED_SEND
            const int64_t now_us = esp_timer_get_time();
#if CONFIG_BANDWIDTH_DROP_LATE_FRAMES
            const int64_t late_us = now_us - next_frame_us;
            const int64_t allowed_late_us = (int64_t)FRAME_INTERVAL_US * CONFIG_BANDWIDTH_MAX_LATE_FRAMES;
            if (late_us > allowed_late_us) {
                const uint32_t stale_slots = (uint32_t)(late_us / FRAME_INTERVAL_US);
                seq += stale_slots;
                dropped_frames += stale_slots;
                next_frame_us += (int64_t)stale_slots * FRAME_INTERVAL_US;
            }
#endif
            if (now_us < next_frame_us) {
                wait_until_us(next_frame_us);
                continue;
            }
#endif

#if CONFIG_BANDWIDTH_50MS_TELEMETRY
            const uint32_t current_telemetry_window =
                (uint32_t)((esp_timer_get_time() - telemetry_start_us) / TELEMETRY_WINDOW_US);
            if (current_telemetry_window != telemetry_window) {
                telemetry_window = current_telemetry_window;
                telemetry_offered = 0;
                telemetry_sent = 0;
                telemetry_dropped = 0;
            }
            telemetry_offered += (uint32_t)tx_batch_frames;
#endif

#if CONFIG_BANDWIDTH_TRANSPORT_UDP && CONFIG_BANDWIDTH_UDP_BLOCKING_FAST_SEND
            fill_frame(frame, seq, telemetry_window, telemetry_offered, telemetry_sent, telemetry_dropped);
            const send_frame_result_t send_result = send_frame_blocking_udp(sock, frame, FRAME_BYTES,
                                                                            &send_fail_events);
#elif CONFIG_BANDWIDTH_TRANSPORT_UDP
            fill_frame(frame, seq, telemetry_window, telemetry_offered, telemetry_sent, telemetry_dropped);
            const send_frame_result_t send_result = send_frame_nonblocking_udp(sock, frame, FRAME_BYTES,
                                                                                 &send_fail_events);
#elif CONFIG_BANDWIDTH_TRANSPORT_TCP && CONFIG_BANDWIDTH_TCP_BATCH_FRAMES > 1
            for (size_t batch_index = 0; batch_index < tx_batch_frames; ++batch_index) {
                fill_frame(frame + batch_index * FRAME_BYTES, seq + (uint32_t)batch_index,
                           telemetry_window, telemetry_offered, telemetry_sent, telemetry_dropped);
            }
#if CONFIG_BANDWIDTH_TCP_BLOCKING_SEND
            const send_frame_result_t send_result = send_frame_blocking_stream(sock, frame, tx_buffer_bytes);
#else
            const send_frame_result_t send_result = send_frame_with_timeout(sock, frame, tx_buffer_bytes);
#endif
#else
            fill_frame(frame, seq, telemetry_window, telemetry_offered, telemetry_sent, telemetry_dropped);
            const send_frame_result_t send_result = send_frame_with_timeout(sock, frame, FRAME_BYTES);
#endif
            if (send_result == SEND_FRAME_OK) {
#if CONFIG_BANDWIDTH_TRANSPORT_UDP
                // Capture the socket-boundary success timestamp before any
                // sender bookkeeping can run after send() returns.
                record_send_success(seq);
#endif
                sent_frames += (uint32_t)tx_batch_frames;
                send_success_count += (uint64_t)tx_batch_frames;
#if CONFIG_BANDWIDTH_50MS_TELEMETRY
                telemetry_sent += (uint32_t)tx_batch_frames;
#endif
            } else if (send_result == SEND_FRAME_DROPPED) {
                dropped_frames += (uint32_t)tx_batch_frames;
#if CONFIG_BANDWIDTH_50MS_TELEMETRY
                telemetry_dropped += (uint32_t)tx_batch_frames;
#endif
#if CONFIG_BANDWIDTH_LOG_DROPPED_FRAMES
                ESP_LOGW(TAG, "Dropped frame seq=%" PRIu32 " after timeout", seq);
#endif
            } else {
#if CONFIG_BANDWIDTH_TRANSPORT_UDP
                fatal_send_errors++;
                diagnostic_fatal_send_errors++;
                ESP_LOGE(TAG, "Fatal UDP send error; keeping seq=%" PRIu32 " and rebuilding socket", seq);
#else
                dropped_frames += (uint32_t)tx_batch_frames;
#if CONFIG_BANDWIDTH_LOG_DROPPED_FRAMES
                ESP_LOGW(TAG, "Dropped frame seq=%" PRIu32 " because socket failed", seq);
#endif
                seq += (uint32_t)tx_batch_frames;
#endif
                break;
            }

            seq += (uint32_t)tx_batch_frames;
#if CONFIG_BANDWIDTH_UNLIMITED_SEND
            next_frame_us = esp_timer_get_time();
#if CONFIG_BANDWIDTH_UNLIMITED_DELAY_EVERY_N_FRAMES > 0
            if ((seq % CONFIG_BANDWIDTH_UNLIMITED_DELAY_EVERY_N_FRAMES) == 0) {
                vTaskDelay(1);
            }
#elif CONFIG_BANDWIDTH_UNLIMITED_YIELD_EVERY_N_FRAMES > 0
            if ((seq % CONFIG_BANDWIDTH_UNLIMITED_YIELD_EVERY_N_FRAMES) == 0) {
                taskYIELD();
            }
#endif
#else
            next_frame_us += (int64_t)FRAME_INTERVAL_US * (int64_t)tx_batch_frames;
#endif

            const int64_t stats_elapsed_us = esp_timer_get_time() - stats_start_us;
            if (stats_elapsed_us >= 1000000) {
#if CONFIG_BANDWIDTH_LOG_STATS
                ESP_LOGI(TAG,
                         "stats sent=%" PRIu32 " dropped=%" PRIu32 " total_seq=%" PRIu32 " rate=%.1f KiB/s "
                         "bp=%" PRIu64 " eagain=%" PRIu64 " enobufs=%" PRIu64 " enomem=%" PRIu64
                         " eintr=%" PRIu64 " fatal=%" PRIu64 " partial=%" PRIu64 " last_errno=%" PRId32
                         " free_heap=%u uptime_ms=%" PRIu32,
                         sent_frames,
                         dropped_frames,
                         seq,
                         (double)sent_frames * FRAME_BYTES * 1000000.0 / stats_elapsed_us / 1024.0,
                         diagnostic_backpressure_events,
                         diagnostic_eagain_events,
                         diagnostic_enobufs_events,
                         diagnostic_enomem_events,
                         diagnostic_eintr_events,
                         diagnostic_fatal_send_errors,
                         diagnostic_partial_send_events,
                         diagnostic_last_errno,
                         (unsigned)esp_get_free_heap_size(),
                         (uint32_t)(esp_timer_get_time() / 1000));
                log_link_diagnostics();
#endif
                sent_frames = 0;
                dropped_frames = 0;
                stats_start_us = esp_timer_get_time();
            }
        }

#if CONFIG_BANDWIDTH_TRANSPORT_TCP
        shutdown(sock, SHUT_RDWR);
#endif
        close(sock);
        if (test_finished) {
            break;
        }
        ESP_LOGW(TAG, "%s disconnected, retrying in 2 seconds",
#if CONFIG_BANDWIDTH_TRANSPORT_UDP
                 "UDP socket"
#else
                 "TCP"
#endif
        );
        vTaskDelay(pdMS_TO_TICKS(2000));
    }

    ESP_LOGI(TAG,
             "UDP sender test finished: send_success_count=%" PRIu64 " send_fail_events=%" PRIu64
             " fatal_send_errors=%" PRIu64 " record_overflow=%" PRIu64
             " send_fail_event_rate=%.6f",
             send_success_count,
             send_fail_events,
             fatal_send_errors,
             send_success_record_overflow,
             (double)send_fail_events /
                 (double)(send_fail_events + send_success_count));
    export_send_success_records(send_fail_events, fatal_send_errors);
    free(send_success_records);
    send_success_records = NULL;
    free(frame);
    vTaskDelete(NULL);
}

void sender_start(void)
{
    xTaskCreate(sender_task, "bandwidth_sender", 8192, NULL, 5, NULL);
}
