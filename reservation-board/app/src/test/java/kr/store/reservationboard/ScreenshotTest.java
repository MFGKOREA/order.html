package kr.store.reservationboard;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.view.View;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;

import java.io.File;
import java.io.FileOutputStream;
import java.util.Collections;

/** 화면 모양 확인용. SCREENSHOT_DIR 환경 변수가 있을 때만 PNG를 남깁니다. */
@RunWith(RobolectricTestRunner.class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class ScreenshotTest {

    @Test
    @Config(qualifiers = "w1280dp-h800dp-land-mdpi")
    public void board() throws Exception {
        android.content.Context ctx = RuntimeEnvironment.getApplication();
        Store s = Store.get(ctx);
        s.clear();
        kr.store.reservationboard.Config.setPackages(ctx, 0, Collections.singleton("com.example.naver"));
        long now = System.currentTimeMillis();
        s.insert(now - 50 * 60_000, 1, "com.example.own", "예약 접수", "이영희님 · 오늘 18:30 · 2명");
        s.insert(now - 35 * 60_000, 0, "com.example.naver", "새로운 예약이 확정되었습니다", "김철수님 · 오늘 19:00 · 4명\n요청사항: 창가 자리 부탁드려요");
        s.markAllSeen();
        s.insert(now - 2 * 60_000, 0, "com.example.naver", "새로운 예약 신청", "박민수님 · 오늘 20:00 · 6명");
        s.insert(now - 60_000, 1, "com.example.own", "예약 접수", "최지우님 · 오늘 20:30 · 3명");

        ActivityController<MainActivity> c = Robolectric.buildActivity(MainActivity.class).setup();
        snap(c.get().getWindow().getDecorView(), "board.png");
    }

    @Test
    @Config(qualifiers = "w1280dp-h800dp-land-mdpi")
    public void settings() throws Exception {
        ActivityController<SettingsActivity> c = Robolectric.buildActivity(SettingsActivity.class).setup();
        snap(c.get().getWindow().getDecorView(), "settings.png");
    }

    private static void snap(View v, String name) throws Exception {
        String dir = System.getenv("SCREENSHOT_DIR");
        if (dir == null) return;
        Bitmap b = Bitmap.createBitmap(v.getWidth(), v.getHeight(), Bitmap.Config.ARGB_8888);
        v.draw(new Canvas(b));
        try (FileOutputStream out = new FileOutputStream(new File(dir, name))) {
            b.compress(Bitmap.CompressFormat.PNG, 100, out);
        }
    }
}
