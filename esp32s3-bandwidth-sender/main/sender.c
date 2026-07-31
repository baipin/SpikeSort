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
#include <unistd.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "lwip/inet.h"
#include "nvs_flash.h"

static const char *TAG = "sender";

#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT BIT1
#define WIFI_MAX_RETRY 10
#define FRAME_HEADER_BYTES 12
#define FRAME_CRC_BYTES 2
#define FRAME_BYTES (FRAME_HEADER_BYTES + CONFIG_BANDWIDTH_PAYLOAD_BYTES + FRAME_CRC_BYTES)
#define FRAME_INTERVAL_US (1000000 / CONFIG_BANDWIDTH_FPS)

static EventGroupHandle_t wifi_event_group;
static int wifi_retry_count;
static bool wall_clock_time_valid;

typedef enum {
    SEND_FRAME_OK,
    SEND_FRAME_DROPPED,
    SEND_FRAME_FATAL,
} send_frame_result_t;

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

static void fill_frame(uint8_t *frame, uint32_t seq)
{
    const uint64_t timestamp_us = current_send_timestamp_us();

    write_u32_le(frame, seq);
    write_u64_le(frame + 4, timestamp_us);

    for (size_t i = 0; i < CONFIG_BANDWIDTH_PAYLOAD_BYTES; ++i) {
        frame[FRAME_HEADER_BYTES + i] = (uint8_t)((seq + i) & 0xff);
    }

    const uint16_t crc = crc16_ccitt_false(frame, FRAME_HEADER_BYTES + CONFIG_BANDWIDTH_PAYLOAD_BYTES);
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

static esp_err_t wifi_init_sta(void)
{
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

    ESP_LOGI(TAG, "Connecting to WiFi SSID: %s", CONFIG_BANDWIDTH_WIFI_SSID);

    const EventBits_t bits = xEventGroupWaitBits(
        wifi_event_group,
        WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
        pdFALSE,
        pdFALSE,
        portMAX_DELAY);

    if (bits & WIFI_CONNECTED_BIT) {
        return ESP_OK;
    }

    ESP_LOGE(TAG, "Failed to connect to WiFi SSID: %s", CONFIG_BANDWIDTH_WIFI_SSID);
    return ESP_FAIL;
}

static void sync_wall_clock_time(void)
{
#if CONFIG_BANDWIDTH_SNTP_ENABLE
    esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG(CONFIG_BANDWIDTH_SNTP_SERVER);
    config.start = true;

    esp_err_t ret = esp_netif_sntp_init(&config);
    if (ret != ESP_OK && ret != ESP_ERR_INVALID_STATE) {
        ESP_LOGW(TAG, "SNTP init failed (%s); using monotonic timestamps", esp_err_to_name(ret));
        wall_clock_time_valid = false;
        return;
    }

    ret = esp_netif_sntp_sync_wait(pdMS_TO_TICKS(CONFIG_BANDWIDTH_SNTP_SYNC_TIMEOUT_MS));
    if (ret == ESP_OK) {
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
    ESP_LOGW(TAG,
             "SNTP sync did not complete within %d ms; using monotonic timestamps",
             CONFIG_BANDWIDTH_SNTP_SYNC_TIMEOUT_MS);
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

    if (CONFIG_BANDWIDTH_SOCKET_SNDBUF > 0) {
        const int send_buffer_bytes = CONFIG_BANDWIDTH_SOCKET_SNDBUF;
        if (setsockopt(sock, SOL_SOCKET, SO_SNDBUF, &send_buffer_bytes, sizeof(send_buffer_bytes)) != 0) {
            ESP_LOGW(TAG, "Failed to set SO_SNDBUF=%d: errno %d", send_buffer_bytes, errno);
        }
    }

    const int flags = fcntl(sock, F_GETFL, 0);
    if (flags >= 0 && fcntl(sock, F_SETFL, flags | O_NONBLOCK) != 0) {
        ESP_LOGW(TAG, "Failed to set socket non-blocking: errno %d", errno);
    }

    return sock;
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

    uint8_t *frame = (uint8_t *)malloc(FRAME_BYTES);
    if (frame == NULL) {
        ESP_LOGE(TAG, "Unable to allocate %u-byte frame buffer", (unsigned)FRAME_BYTES);
        vTaskDelete(NULL);
        return;
    }

    uint32_t seq = 0;
    uint32_t sent_frames = 0;
    uint32_t dropped_frames = 0;
    int64_t stats_start_us = esp_timer_get_time();
    int64_t next_frame_us = stats_start_us;

    ESP_LOGI(TAG,
             "Phase 5 calibrated sender: payload=%d bytes, frame=%u bytes, fps=%d, timeout=%d ms, timestamp=%s",
             CONFIG_BANDWIDTH_PAYLOAD_BYTES,
             (unsigned)FRAME_BYTES,
             CONFIG_BANDWIDTH_FPS,
             CONFIG_BANDWIDTH_SEND_TIMEOUT_MS,
             wall_clock_time_valid ? "epoch_us" : "monotonic_us");

    while (true) {
        int sock = connect_tcp_server();
        if (sock < 0) {
            vTaskDelay(pdMS_TO_TICKS(2000));
            continue;
        }
        next_frame_us = esp_timer_get_time();

        while (true) {
            const int64_t now_us = esp_timer_get_time();
            if (now_us < next_frame_us) {
                const int64_t sleep_ms = (next_frame_us 