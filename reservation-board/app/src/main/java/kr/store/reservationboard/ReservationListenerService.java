package kr.store.reservationboard;

import android.app.Notification;
import android.content.ComponentName;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

/**
 * 태블릿에 뜨는 알림 중 설정에서 고른 앱(네이버, 자사앱)의 알림만 골라 알림판에 기록합니다.
 * 알림 내용은 태블릿 밖으로 나가지 않습니다.
 */
public class ReservationListenerService extends NotificationListenerService {

    @Override
    public void onListenerConnected() {
        Board.connected = true;
        Board.status();
        // 앱이 꺼져 있던 사이에 쌓인 알림도 소리 없이 가져옵니다.
        try {
            StatusBarNotification[] active = getActiveNotifications();
            if (active != null) {
                for (StatusBarNotification sbn : active) handle(sbn, false);
            }
        } catch (RuntimeException ignored) {
            // 연결 직후 드물게 실패할 수 있어요. 다음 알림부터는 정상 수신됩니다.
        }
    }

    @Override
    public void onListenerDisconnected() {
        Board.connected = false;
        Board.status();
        requestRebind(new ComponentName(this, ReservationListenerService.class));
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        handle(sbn, true);
    }

    private void handle(StatusBarNotification sbn, boolean alert) {
        String pkg = sbn.getPackageName();
        if (pkg.equals(getPackageName())) return;
        Config.markSeen(this, pkg);

        int source = Config.sourceFor(this, pkg);
        if (source < 0) return;

        Notification n = sbn.getNotification();
        if ((n.flags & Notification.FLAG_GROUP_SUMMARY) != 0 || sbn.isOngoing()) return;

        Bundle ex = n.extras;
        String title = first(ex.getCharSequence(Notification.EXTRA_TITLE_BIG),
                ex.getCharSequence(Notification.EXTRA_TITLE));
        String body = first(ex.getCharSequence(Notification.EXTRA_BIG_TEXT),
                ex.getCharSequence(Notification.EXTRA_TEXT));
        CharSequence[] lines = ex.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
        if (body.isEmpty() && lines != null) {
            StringBuilder sb = new StringBuilder();
            for (CharSequence line : lines) {
                if (line == null) continue;
                if (sb.length() > 0) sb.append('\n');
                sb.append(line);
            }
            body = sb.toString().trim();
        }
        if (title.isEmpty() && body.isEmpty()) return;
        if (!Config.matches(this, source, title + "\n" + body)) return;

        Entry e = Store.get(this).insert(sbn.getPostTime(), source, pkg, title, body);
        if (e == null) return;
        if (n.contentIntent != null) Board.intents.put(e.id, n.contentIntent);
        if (alert) Alerter.get(this).alert(source);
        Board.publish(e);
    }

    private static String first(CharSequence a, CharSequence b) {
        if (a != null && a.toString().trim().length() > 0) return a.toString().trim();
        return b == null ? "" : b.toString().trim();
    }
}
