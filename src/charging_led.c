/*
 * 充電状態を状態表示の RGB LED に出す（CONFIG_SOSHO_CHARGING_LED）。
 *
 * XIAO nRF52840 の充電 IC（BQ25101）の CHG 信号（P0.17。充電中は Low）と、
 * nRF52840 の USB 給電の検出（VBUS）を読み、zmk-rgbled-widget の LED に出す。
 *   充電中:   黄をフェード（呼吸）。PWM で明るさを変える
 *   完了:     緑を点灯（USB を抜くまで）。CHG が High で、電池電圧が満充電に近いとき
 *   要確認:   赤をフェード。CHG が High なのに電池電圧が低いとき
 *             （10 時間の安全タイマーで充電 IC が止まったときなど）
 *   USB なし: 何も出さない（widget の表示のまま）
 * 信号を読むだけで、充電の動き（充電電流を切り替える P0.13 など）には触らない。
 * USB の給電は POWER のレジスタ（VBUS の検出）で直接見る。USB の通信の状態に左右されない。
 *
 * LED のピン（赤・緑）は widget の GPIO と PWM（sosho.dtsi の &pwm1）で共有している。
 * PWM が止まっている間は GPIO の出力のレジスタがピンを決め、PWM が動いている間は PWM が決める
 * （Zephyr の pwm_nrfx の仕組み）。widget が何かを表示しようとしたら（出力のレジスタで LED を点けた、
 * または表示待ちの列に項目がある）、フェードを止めて LED を widget に返す。
 *
 * widget の内部（led_msgq・led_layer_color・led_current_color・struct blink_item）に頼っている。
 * widget の版を上げたら、これらが変わっていないかを確かめる（docs/workflow.html#zmk-update）。
 */

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/led.h>
#include <zephyr/drivers/pwm.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/init.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>

#include <hal/nrf_gpio.h>
#include <hal/nrf_power.h>

#include <zmk/event_manager.h>
#include <zmk/events/activity_state_changed.h>
#include <zmk/workqueue.h>

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

/* 色の値は widget と同じ（ビット 0 = 赤、1 = 緑、2 = 青） */
#define COLOR_OFF 0
#define COLOR_GREEN 2

#define POLL_MS 1000          /* 信号を読む間隔 */
#define FADE_TICK_MS 20       /* フェードの明るさを変える間隔 */
#define STABLE_MS 3000        /* 同じ状態がこの時間続いたら確定する（つないだ直後の揺れを拾わない） */
#define START_DELAY_MS 3000   /* 起動時の widget の表示（電池残量・接続状態）を先に出させる */
#define RECHECK_MV_MS 60000   /* 充電が止まっている間、電池電圧を測り直す間隔 */
/* デューティの上限（‰）。100 % にするとドライバが PWM を止めて出力のレジスタを点灯に書き換え、
   widget の表示と見分けられなくなるので、少し手前で止める */
#define DUTY_MAX 990

/* zmk-rgbled-widget の src/widget.c にある定義と同じ並び。widget の版を上げたら突き合わせる */
struct blink_item {
    uint8_t color;
    uint32_t duration_ms;
    uint32_t sleep_ms;
};

/* widget の表示待ちの列、点滅のあとに戻す色、いま点いている色（どれも widget.c の大域変数） */
extern struct k_msgq led_msgq;
extern uint8_t led_layer_color;
extern uint8_t led_current_color;

#define ZEPHYR_USER DT_PATH(zephyr_user)

BUILD_ASSERT(DT_NODE_HAS_PROP(ZEPHYR_USER, chg_gpios),
             "sosho.dtsi の zephyr,user に chg-gpios（充電 IC の CHG 信号）が要る");
BUILD_ASSERT(DT_NODE_HAS_PROP(ZEPHYR_USER, pwms),
             "sosho.dtsi の zephyr,user に pwms（LED の赤・緑の PWM）が要る");
BUILD_ASSERT(DT_HAS_CHOSEN(zmk_battery), "電池電圧を測るデバイス（chosen の zmk,battery）が要る");

static const struct gpio_dt_spec chg = GPIO_DT_SPEC_GET(ZEPHYR_USER, chg_gpios);
static const struct pwm_dt_spec pwm_red = PWM_DT_SPEC_GET_BY_NAME(ZEPHYR_USER, red);
static const struct pwm_dt_spec pwm_green = PWM_DT_SPEC_GET_BY_NAME(ZEPHYR_USER, green);
static const struct device *const battery = DEVICE_DT_GET(DT_CHOSEN(zmk_battery));

/* widget の LED（寝る直前に直接消すのと、出力のレジスタで widget の表示を知るのに使う） */
static const struct device *const led_dev = DEVICE_DT_GET(DT_COMPAT_GET_ANY_STATUS_OKAY(gpio_leds));
static const uint8_t rgb_idx[] = {DT_NODE_CHILD_IDX(DT_ALIAS(led_red)),
                                  DT_NODE_CHILD_IDX(DT_ALIAS(led_green)),
                                  DT_NODE_CHILD_IDX(DT_ALIAS(led_blue))};

#define LED_IS_GPIO0(alias) DT_SAME_NODE(DT_GPIO_CTLR(DT_ALIAS(alias), gpios), DT_NODELABEL(gpio0))
BUILD_ASSERT(LED_IS_GPIO0(led_red) && LED_IS_GPIO0(led_green) && LED_IS_GPIO0(led_blue),
             "LED のピンは P0.xx の前提（出力のレジスタを直接読む）");
#define LED_PIN(alias) DT_GPIO_PIN(DT_ALIAS(alias), gpios)
#define LED_ON_LEVEL(alias) ((DT_GPIO_FLAGS(DT_ALIAS(alias), gpios) & GPIO_ACTIVE_LOW) ? 0 : 1)

static const struct {
    uint32_t pin;
    uint32_t on_level;
} widget_leds[] = {
    {LED_PIN(led_red), LED_ON_LEVEL(led_red)},
    {LED_PIN(led_green), LED_ON_LEVEL(led_green)},
    {LED_PIN(led_blue), LED_ON_LEVEL(led_blue)},
};

/* 信号から読んだ状態 */
enum signal {
    SIGNAL_NO_USB,   /* USB からの給電が無い */
    SIGNAL_CHARGING, /* 給電あり、CHG が Low（充電中） */
    SIGNAL_STOPPED,  /* 給電あり、CHG が High（充電が止まった） */
};

/* LED に出す状態 */
enum indication {
    SHOW_NONE,     /* 何も出さない */
    SHOW_CHARGING, /* 黄のフェード */
    SHOW_DONE,     /* 緑の点灯 */
    SHOW_CHECK,    /* 赤のフェード */
};

static const char *const indication_names[] = {"none", "charging", "done", "check"};

static struct k_work_delayable tick_work;
static atomic_t sleeping;     /* deep sleep に入るところ。LED に何も出さない */
static atomic_t needs_reset;  /* 寝るのに失敗して起きたので、状態を初めからやり直す */

/* ここから下の変数は tick()（低優先度のキュー）だけが触る。
   例外は SLEEP のリスナーで、tick() を止めて終わるのを待ってから触る */
static enum signal candidate = SIGNAL_NO_USB;
static int64_t candidate_since;
static enum signal confirmed = SIGNAL_NO_USB;
static enum indication shown = SHOW_NONE;
static bool rest_color_pending; /* 点灯・消灯の指示をまだ widget に渡せていない */
static bool fade_running;       /* PWM が LED を光らせている */
static int64_t last_poll;
static int64_t last_mv_check;

static int read_signal(enum signal *out) {
    if (!nrf_power_usbregstatus_vbusdet_get(NRF_POWER)) {
        *out = SIGNAL_NO_USB;
        return 0;
    }
    int val = gpio_pin_get_dt(&chg);
    if (val < 0) {
        return val;
    }
    *out = val ? SIGNAL_CHARGING : SIGNAL_STOPPED;
    return 0;
}

/* 電池電圧 (mV)。ZMK の電池の測定と同じ低優先度のキューで動くので、測定が重ならない */
static int read_battery_mv(void) {
    struct sensor_value v;
    int rc = sensor_sample_fetch_chan(battery, SENSOR_CHAN_GAUGE_VOLTAGE);
    if (rc == 0) {
        rc = sensor_channel_get(battery, SENSOR_CHAN_GAUGE_VOLTAGE, &v);
    }
    if (rc != 0) {
        return rc;
    }
    return v.val1 * 1000 + v.val2 / 1000;
}

/* 充電が止まったときの表示。満充電に近ければ完了、そうでなければ要確認（読めないときも要確認） */
static enum indication stopped_indication(void) {
    int mv = read_battery_mv();
    LOG_DBG("Charging LED: charger stopped, battery %d mV", mv);
    return mv >= CONFIG_SOSHO_CHARGING_LED_FULL_MV ? SHOW_DONE : SHOW_CHECK;
}

static int put_item(uint8_t color, uint32_t duration_ms) {
    if (atomic_get(&sleeping)) {
        return -EAGAIN;
    }
    struct blink_item item = {.color = color, .duration_ms = duration_ms};
    int rc = k_msgq_put(&led_msgq, &item, K_NO_WAIT);
    /* 入れている間に寝ることが決まったら、寝ている間に点かないよう取り消す */
    if (atomic_get(&sleeping)) {
        k_msgq_purge(&led_msgq);
        return -EAGAIN;
    }
    return rc;
}

/* widget が何かを表示しようとしているか。PWM が光らせている間も、出力のレジスタには widget の書いた値が残る */
static bool widget_busy(void) {
    if (k_msgq_num_used_get(&led_msgq) > 0) {
        return true;
    }
    for (size_t i = 0; i < ARRAY_SIZE(widget_leds); i++) {
        if (nrf_gpio_pin_out_read(widget_leds[i].pin) == widget_leds[i].on_level) {
            return true;
        }
    }
    return false;
}

static void set_duty(const struct pwm_dt_spec *spec, uint32_t permille) {
    static bool warned;
    int rc = pwm_set_pulse_dt(spec, (uint32_t)((uint64_t)spec->period * MIN(permille, DUTY_MAX) / 1000));
    /* 20 ms ごとに呼ぶので、ログは最初の 1 回だけ */
    if (rc != 0 && !warned) {
        LOG_WRN("Charging LED: failed to set PWM (%d)", rc);
        warned = true;
    }
}

/* フェードを止めて、LED を widget に返す */
static void stop_fade(void) {
    if (!fade_running) {
        return;
    }
    /* デューティ 0 にするとドライバが出力のレジスタを消灯に書き換えるので、widget が書いた値に戻す。
       widget_leds[0]・[1] は pwm_red・pwm_green と同じピン（sosho.dtsi の pwm1_led_default） */
    uint32_t red = nrf_gpio_pin_out_read(widget_leds[0].pin);
    uint32_t green = nrf_gpio_pin_out_read(widget_leds[1].pin);
    set_duty(&pwm_red, 0);
    set_duty(&pwm_green, 0);
    nrf_gpio_pin_write(widget_leds[0].pin, red);
    nrf_gpio_pin_write(widget_leds[1].pin, green);
    fade_running = false;
}

/* 呼吸の明るさ。デューティ（‰）で返す */
static uint32_t breath_duty(int64_t now) {
    const uint32_t period = MAX(CONFIG_SOSHO_CHARGING_LED_FADE_PERIOD_MS, 2 * FADE_TICK_MS);
    const uint32_t half = period / 2;
    uint32_t t = (uint32_t)(now % period);
    /* 0 → 1000 → 0 の三角波を、端がなめらかになるよう smoothstep で丸める */
    uint64_t p = t < half ? (uint64_t)t * 1000 / half : (uint64_t)(period - t) * 1000 / half;
    p = MIN(p, 1000); /* 周期が奇数のとき、端で 1000 を少し超えるため */
    uint64_t s = p * p * (3000 - 2 * p) / 1000000;
    /* 見た目の明るさ（‰）。いちばん暗いときも最低限の明るさを残す */
    uint64_t min = CONFIG_SOSHO_CHARGING_LED_FADE_MIN_PCT * 10;
    uint64_t look = min + (1000 - min) * s / 1000;
    /* 目の感じ方に合わせて 2 乗する（ガンマ 2） */
    return (uint32_t)(look * look / 1000);
}

static void set_indication(enum indication next, int64_t now) {
    if (next == shown) {
        return;
    }
    LOG_INF("Charging LED: %s -> %s", indication_names[shown], indication_names[next]);

    /* 緑の点灯は、widget が点滅のあとに戻す色を緑にして作る。やめるときは消灯に戻す */
    if (next == SHOW_DONE || shown == SHOW_DONE) {
        led_layer_color = next == SHOW_DONE ? COLOR_GREEN : COLOR_OFF;
        rest_color_pending = true;
    }
    shown = next;
}

static void poll_signal(int64_t now) {
    enum signal sig;
    if (read_signal(&sig) == 0) {
        if (sig != candidate) {
            candidate = sig;
            candidate_since = now;
        } else if (sig != confirmed && now - candidate_since >= STABLE_MS) {
            confirmed = sig;
            switch (sig) {
            case SIGNAL_NO_USB:
                set_indication(SHOW_NONE, now);
                break;
            case SIGNAL_CHARGING:
                set_indication(SHOW_CHARGING, now);
                break;
            case SIGNAL_STOPPED:
                set_indication(stopped_indication(), now);
                last_mv_check = now;
                break;
            }
        }
    }

    /* 充電が止まっている間は電圧を測り直す（止まった直後の電圧は高めに出ることがあるため） */
    if (confirmed == SIGNAL_STOPPED && now - last_mv_check >= RECHECK_MV_MS) {
        set_indication(stopped_indication(), now);
        last_mv_check = now;
    }
}

static void update_led(int64_t now) {
    if (rest_color_pending) {
        /* 長さ 0 の項目は、widget がその色にしたままにする */
        rest_color_pending = put_item(led_layer_color, 0) != 0;
    }

    if ((shown != SHOW_CHARGING && shown != SHOW_CHECK) || widget_busy()) {
        stop_fade();
        return;
    }

    uint32_t duty = breath_duty(now);
    if (shown == SHOW_CHARGING) {
        set_duty(&pwm_red, duty * CONFIG_SOSHO_CHARGING_LED_YELLOW_RED_PCT / 100);
        set_duty(&pwm_green, duty);
    } else {
        set_duty(&pwm_red, duty);
        set_duty(&pwm_green, 0);
    }
    fade_running = true;
}

static void tick(struct k_work *work) {
    if (atomic_get(&sleeping)) {
        return;
    }
    int64_t now = k_uptime_get();

    if (atomic_cas(&needs_reset, 1, 0)) {
        candidate = confirmed = SIGNAL_NO_USB;
        candidate_since = now;
        shown = SHOW_NONE;
        rest_color_pending = false;
    }

    if (now - last_poll >= POLL_MS) {
        last_poll = now;
        poll_signal(now);
    }
    update_led(now);

    /* フェードする状態の間は、widget の表示で止めているときも短い間隔で見て、すぐに再開する */
    bool fading_state = shown == SHOW_CHARGING || shown == SHOW_CHECK;
    k_work_schedule_for_queue(zmk_workqueue_lowprio_work_q(), &tick_work,
                              K_MSEC(fading_state ? FADE_TICK_MS : POLL_MS));
}

static int charging_led_activity_listener(const zmk_event_t *eh) {
    const struct zmk_activity_state_changed *ev = as_zmk_activity_state_changed(eh);
    if (ev == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    if (ev->state == ZMK_ACTIVITY_SLEEP) {
        /* deep sleep の間も LED のピンは状態を保つので、点いたままにならないよう直接消す。
           ZMK は USB から給電されている間は寝ないので、ここに来るのはふつう USB を抜いたあと */
        atomic_set(&sleeping, 1);
        struct k_work_sync sync;
        k_work_cancel_delayable_sync(&tick_work, &sync);
        if (fade_running) {
            set_duty(&pwm_red, 0);
            set_duty(&pwm_green, 0);
            fade_running = false;
        }
        k_msgq_purge(&led_msgq);
        led_layer_color = COLOR_OFF;
        for (size_t i = 0; i < ARRAY_SIZE(rgb_idx); i++) {
            led_off(led_dev, rgb_idx[i]);
        }
        led_current_color = COLOR_OFF;
    } else if (atomic_cas(&sleeping, 1, 0)) {
        atomic_set(&needs_reset, 1);
        k_work_schedule_for_queue(zmk_workqueue_lowprio_work_q(), &tick_work, K_NO_WAIT);
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(charging_led, charging_led_activity_listener);
ZMK_SUBSCRIPTION(charging_led, zmk_activity_state_changed);

static int charging_led_init(void) {
    /* widget の点滅の項目の大きさが変わっていたら、並びも変わっているかもしれないので動かさない */
    if (led_msgq.msg_size != sizeof(struct blink_item)) {
        LOG_ERR("Charging LED: blink item size mismatch with rgbled-widget, disabled");
        return -EINVAL;
    }
    if (!gpio_is_ready_dt(&chg) || !pwm_is_ready_dt(&pwm_red) || !pwm_is_ready_dt(&pwm_green)) {
        LOG_ERR("Charging LED: CHG GPIO or LED PWM not ready");
        return -ENODEV;
    }
    int rc = gpio_pin_configure_dt(&chg, GPIO_INPUT);
    if (rc != 0) {
        LOG_ERR("Charging LED: failed to configure CHG GPIO (%d)", rc);
        return rc;
    }
    /* 電圧を測れないと、充電が止まったときはいつも「要確認」になる */
    if (!device_is_ready(battery)) {
        LOG_WRN("Charging LED: battery device not ready, completion will show as check");
    }

    k_work_init_delayable(&tick_work, tick);
    k_work_schedule_for_queue(zmk_workqueue_lowprio_work_q(), &tick_work, K_MSEC(START_DELAY_MS));
    return 0;
}

SYS_INIT(charging_led_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
