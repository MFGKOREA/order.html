package kr.store.reservationboard;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;

import java.util.Collections;

@RunWith(RobolectricTestRunner.class)
public class BridgeTest {
    private Context ctx;
    private Bridge bridge;

    @Before
    public void setUp() {
        ctx = RuntimeEnvironment.getApplication();
        Store.get(ctx).clear();
        Config.setPackages(ctx, 0, Collections.singleton("com.example.naver"));
        Config.setPackages(ctx, 1, Collections.singleton("com.example.own"));
        Config.setName(ctx, 1, "우리앱");
        bridge = new Bridge(Robolectric.buildActivity(MainActivity.class).setup().get());
    }

    @Test
    public void stateCarriesEntriesSourcesAndIcons() throws Exception {
        long now = System.currentTimeMillis();
        Store.get(ctx).insert(now - 60_000, 0, "com.example.naver", "새로운 예약", "김철수 19:00 4명");
        Store.get(ctx).insert(now - 3 * 24 * 3600_000L, 1, "com.example.own", "예약 접수", "오래된 예약");

        JSONObject state = new JSONObject(bridge.state());
        JSONArray entries = state.getJSONArray("entries");
        assertEquals("이틀이 넘은 기록은 화면에 보내지 않아요", 1, entries.length());
        assertEquals("새로운 예약", entries.getJSONObject(0).getString("title"));
        assertTrue(entries.getJSONObject(0).getBoolean("isNew"));
        assertEquals("우리앱", state.getJSONArray("sources").getJSONObject(1).getString("name"));
        assertTrue(state.getJSONObject("icons").getString("com.example.naver").endsWith("/icon/com.example.naver"));
    }

    @Test
    public void ackMarksEntrySeen() throws Exception {
        Entry e = Store.get(ctx).insert(System.currentTimeMillis(), 0, "com.example.naver", "새로운 예약", "A");
        bridge.ack(String.valueOf(e.id));
        JSONObject state = new JSONObject(bridge.state());
        assertFalse(state.getJSONArray("entries").getJSONObject(0).getBoolean("isNew"));
    }

    @Test
    public void anAppBelongsToOneSourceOnly() throws Exception {
        bridge.setPackages("1", "[\"com.example.naver\",\"com.example.own\"]");
        assertTrue(Config.packages(ctx, 0).isEmpty());
        assertEquals(2, Config.packages(ctx, 1).size());
    }

    @Test
    public void savesNamesKeywordsAndSettings() throws Exception {
        bridge.saveSource("0", "{\"name\":\"네이버예약\",\"keywords\":\"예약, 주문\"}");
        bridge.setSetting("textSize", "2");
        bridge.setSetting("voice", "false");
        assertEquals("네이버예약", Config.name(ctx, 0));
        assertTrue(Config.matches(ctx, 0, "새 주문이 왔어요"));
        assertFalse(Config.matches(ctx, 0, "리뷰가 달렸어요"));
        assertEquals(2, Config.textSize(ctx));
        assertFalse(Config.voice(ctx));
    }
}
