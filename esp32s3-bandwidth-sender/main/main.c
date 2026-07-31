#include "esp_log.h"

#include "sender.h"

static const char *TAG = "bandwidth_sender";

void app_main(void)
{
    ESP_LOGI(TAG, "Starting ESP32-S3 bandwidth sender");
    sender_start();
}
