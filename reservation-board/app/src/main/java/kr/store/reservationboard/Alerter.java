package kr.store.reservationboard;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.speech.tts.TextToSpeech;

import java.util.Locale;

/** 새 예약이 오면 알림음과 음성 안내로 알려 줍니다. 바쁜 홀에서도 들리도록 알람 볼륨을 씁니다. */
final class Alerter implements TextToSpeech.OnInitListener {
    private static final AudioAttributes LOUD = new AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_ALARM)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build();

    private static Alerter instance;

    private final Context app;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextToSpeech tts;
    private boolean ttsReady;

    static synchronized Alerter get(Context c) {
        if (instance == null) instance = new Alerter(c.getApplicationContext());
        return instance;
    }

    private Alerter(Context app) {
        this.app = app;
    }

    void alert(int source) {
        if (Config.sound(app)) playTone();
        if (Config.voice(app)) {
            String phrase = Config.name(app, source) + " 새 예약 알림";
            handler.postDelayed(() -> speak(phrase), Config.sound(app) ? 1500 : 0);
        }
    }

    private void playTone() {
        Uri uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
        Ringtone r = RingtoneManager.getRingtone(app, uri);
        if (r == null) return;
        r.setAudioAttributes(LOUD);
        r.play();
    }

    private void speak(String phrase) {
        if (tts == null) {
            tts = new TextToSpeech(app, this);
            tts.setAudioAttributes(LOUD);
            // 엔진 준비가 끝나면 onInit에서 말합니다.
            handler.postDelayed(() -> speak(phrase), 1500);
            return;
        }
        if (!ttsReady) return;
        tts.speak(phrase, TextToSpeech.QUEUE_ADD, null, "board-" + System.nanoTime());
    }

    @Override
    public void onInit(int status) {
        if (status != TextToSpeech.SUCCESS) return;
        tts.setLanguage(Locale.KOREAN);
        ttsReady = true;
    }
}
