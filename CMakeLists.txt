# このリポジトリ独自のファームウェアのコード。zephyr/module.yml でモジュールとして読み込まれる
target_sources_ifdef(CONFIG_SOSHO_CHARGING_LED app PRIVATE src/charging_led.c)
