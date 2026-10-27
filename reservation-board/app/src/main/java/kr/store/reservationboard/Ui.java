package kr.store.reservationboard;

import android.content.ComponentName;
import android.content.Context;
import android.graphics.Insets;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.provider.Settings;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.TextView;

/** 화면 코드에서 같이 쓰는 색과 작은 도우미들. */
final class Ui {
    static final int BG = 0xFF0F1216;
    static final int CARD = 0xFF1B2027;
    static final int CARD_NEW = 0xFF22303F;
    static final int TEXT = 0xFFF2F4F7;
    static final int SUB = 0xFF9AA4B2;
    static final int NEW = 0xFFFFC53D;
    static final int OK = 0xFF22C55E;
    static final int WARN = 0xFFEF4444;
    static final int CHIP = 0xFF2A313B;

    private Ui() {}

    static int dp(Context c, float v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v,
                c.getResources().getDisplayMetrics()));
    }

    static GradientDrawable round(Context c, int color, float radiusDp) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(color);
        d.setCornerRadius(dp(c, radiusDp));
        return d;
    }

    static TextView text(Context c, String s, float sp, int color, boolean bold) {
        TextView t = new TextView(c);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    /** 손가락으로 누르기 쉬운 크기의 둥근 버튼. */
    static TextView button(Context c, String label, int bg) {
        TextView b = text(c, label, 18, TEXT, true);
        b.setGravity(Gravity.CENTER);
        b.setMinHeight(dp(c, 52));
        b.setPadding(dp(c, 20), dp(c, 10), dp(c, 20), dp(c, 10));
        b.setBackground(round(c, bg, 14));
        b.setClickable(true);
        b.setFocusable(true);
        return b;
    }

    /** 안드로이드 15부터는 화면이 상태바 아래까지 그려지므로 그만큼 여백을 줍니다. */
    static void fitSystemBars(View root) {
        if (Build.VERSION.SDK_INT < 35) return;
        int l = root.getPaddingLeft(), t = root.getPaddingTop(), r = root.getPaddingRight(), b = root.getPaddingBottom();
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            Insets i = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            v.setPadding(l + i.left, t + i.top, r + i.right, b + i.bottom);
            return WindowInsets.CONSUMED;
        });
    }

    static boolean listenerEnabled(Context c) {
        String flat = Settings.Secure.getString(c.getContentResolver(), "enabled_notification_listeners");
        if (flat == null) return false;
        String full = new ComponentName(c, ReservationListenerService.class).flattenToString();
        String shortName = new ComponentName(c, ReservationListenerService.class).flattenToShortString();
        for (String item : flat.split(":")) {
            if (item.equals(full) || item.equals(shortName)) return true;
        }
        return false;
    }
}
