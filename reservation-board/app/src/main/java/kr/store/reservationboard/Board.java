package kr.store.reservationboard;

import android.app.PendingIntent;
import android.os.Handler;
import android.os.Looper;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/** 알림 수신 서비스와 화면을 이어 줍니다. 같은 앱 프로세스 안에서만 씁니다. */
final class Board {
    interface Listener {
        void onEntry(Entry e);

        void onStatus();
    }

    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static Listener listener;

    /** 시스템이 알림 수신 서비스를 연결해 둔 상태인지. */
    static volatile boolean connected;

    /** 항목을 눌렀을 때 원래 앱의 해당 화면을 열기 위한 알림 인텐트. 앱이 재시작되면 사라집니다. */
    static final Map<Long, PendingIntent> intents = new ConcurrentHashMap<>();

    private Board() {}

    static void setListener(Listener l) {
        listener = l;
    }

    static void publish(Entry e) {
        MAIN.post(() -> {
            if (listener != null) listener.onEntry(e);
        });
    }

    static void status() {
        MAIN.post(() -> {
            if (listener != null) listener.onStatus();
        });
    }
}
