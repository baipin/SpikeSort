idf_component_register(
    SRCS "main.c" "sender.c"
    INCLUDE_DIRS "."
    REQUIRES esp_event esp_netif esp_timer esp_wifi nvs_flash
)
