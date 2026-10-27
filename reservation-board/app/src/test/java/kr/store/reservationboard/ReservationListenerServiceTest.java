package kr.store.reservationboard;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import android.app.Notification;
import android.content.Context;
import android.os.Process;
import android.service.notification.StatusBarNotification;

import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;

import java.util.Collections;
import java.util.List;

@RunWith(RobolectricTestRunner.class)
public class ReservationListenerServiceTest {
    private static final String NAVER = "com.example.naver";
    private static final String OWN = "com.example.own";
    private static final String OTHER = "com.example.other";

    private Context ctx;
    private ReservationListenerService service;
    private int nextId;

    @Before
    public void setUp() {
        ctx = RuntimeEnvironment.getApplication();
        Store.get(ctx).clear();
        Config.setPackages(ctx, 0, Collections.singleton(NAVER));
        Config.setPackages(ctx, 1, Collections.singleton(OWN));
        Config.setKeywords(ctx, 0, "");
        Config.setKeywords(ctx, 1, "");
        Config.setSound(ctx, false);
        Config.setVoice(ctx, false);
        service = Robolectric.setupService(ReservationListenerService.class);
    }

    private StatusBarNotification post(String pkg, String title, String text, long when, boolean summary) {
        Notification.Builder b = new Notification.Builder(ctx, "c")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title)
                .setContentText(text);
        if (summary) b.setGroup("g").setGroupSummary(true);
        StatusBarNotification sbn = new StatusBarNotification(pkg, pkg, nextId++, null, Process.myUid(), 0, 0,
                b.build(), Process.myUserHandle(), when);
        service.onNotificationPosted(sbn);
        return sbn;
    }

    private List<Entry> all() {
        return Store.get(ctx).recent(0, -1);
    }

    @Test
    public void recordsConfiguredAppsUnderTheirSource() {
        long now = System.currentTimeMillis();
        post(NAVER, "새로운 예약", "김철수 19:00 4명", now, false);
        post(OWN, "예약 접수", "이영희 19:30 2명", now + 1, false);
        post(OTHER, "광고", "할인!", now + 2, false);

        List<Entry> entries = all();
        assertEquals(2, entries.size());
        assertEquals(1, entries.get(0).source);
        assertEquals("예약 접수", entries.get(0).title);
        assertEquals(0, entries.get(1).source);
        assertEquals("김철수 19:00 4명", entries.get(1).body);
        assertTrue(entries.get(0).isNew);
    }

    @Test
    public void repostedNotificationIsRecordedOnce() {
        long now = System.currentTimeMillis();
        post(NAVER, "새로운 예약", "김철수 19:00 4명", now, false);
        post(NAVER, "새로운 예약", "김철수 19:00 4명", now + 5_000, false);
        assertEquals(1, all().size());
    }

    @Test
    public void groupSummaryIsIgnored() {
        post(NAVER, "예약 2건", "새 예약이 2건 있어요", System.currentTimeMillis(), true);
        assertEquals(0, all().size());
    }

    @Test
    public void keywordFilterKeepsOnlyMatchingNotifications() {
        Config.setKeywords(ctx, 0, "예약, 주문");
        long now = System.currentTimeMillis();
        post(NAVER, "새 리뷰", "별점 5점 리뷰가 등록됐어요", now, false);
        post(NAVER, "새로운 예약", "김철수 19:00 4명", now + 1, false);
        List<Entry> entries = all();
        assertEquals(1, entries.size());
        assertEquals("새로운 예약", entries.get(0).title);
    }

    @Test
    public void countsAndAcknowledge() {
        long now = System.currentTimeMillis();
        post(NAVER, "새로운 예약", "A", now, false);
        post(NAVER, "새로운 예약", "B", now + 1, false);
        post(OWN, "예약 접수", "C", now + 2, false);
        int[] counts = Store.get(ctx).countsSince(now - 1000);
        assertEquals(2, counts[0]);
        assertEquals(1, counts[1]);
        assertEquals(3, Store.get(ctx).newCount());
        Store.get(ctx).markAllSeen();
        assertEquals(0, Store.get(ctx).newCount());
    }
}
