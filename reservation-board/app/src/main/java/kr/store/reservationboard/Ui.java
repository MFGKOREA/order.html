package kr.store.reservationboard;

import android.content.ComponentName;
import android.content.Context;
import android.graphics.Insets;
import android.os.Build;
import android.provider.Settings;
import android.view.View;
import android.view.WindowInsets;

/** 화면 쪽에서 같이 쓰는 작은 도우미들. */
final class Ui {
    private Ui() {}

    /** 안드로이드 15부터는 화면이 상태바 아래까지 그려지므로 그만큼 여백을 줍니다. */
    static void fitSystemBars(View root) {
        if (Build.VERSION.SDK_INT < 35) return;
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            Insets i = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            v.setPadding(i.left, i.top, i.right, i.bottom);
            return WindowInsets.CONSUMED;
        });
    }

    static boolean listenerEnabled(Context c) {
        String flat = Settings.Secure.getString(c.getContentResolver(), "enabled_notification_listeners");
        if (flat == null) return false;
        ComponentName cn = new ComponentName(c, ReservationListenerService.class);
        for (String item : flat.split(":")) {
            if (item.equals(cn.flattenToString()) || item.equals(cn.flattenToShortString())) return true;
        }
        return false;
    }
}
