package se.tvcal.pqprobe;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Point;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.VideoView;

import java.io.File;

/**
 * Enfärgad helskärm, eller en centrerad ruta mot svart, som mätaren kan läsa av.
 *
 * am start -n se.tvcal.pqprobe/.PatternActivity [--es color ffffff] [--ei window 10]
 * window = rutans andel av skärmytan i procent. Utelämnad eller 100 ger helskärm.
 *
 * am start -n se.tvcal.pqprobe/.PatternActivity --es video white10.mp4
 * spelar en videofil i slinga från /sdcard/Android/data/se.tvcal.pqprobe/files/.
 */
public class PatternActivity extends Activity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        String hex = getIntent().getStringExtra("color");
        int color = Color.parseColor("#" + (hex == null ? "ffffff" : hex));
        int percent = getIntent().getIntExtra("window", 100);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        // Video visas i videoplanet, där TV:ns bildbehandling verkar; en vanlig vy hamnar i
        // grafikplanet. Filen läses från appens egen mapp så att ingen lagringsbehörighet behövs.
        String video = getIntent().getStringExtra("video");
        if (video != null) {
            final VideoView view = new VideoView(this);
            view.setVideoPath(new File(getExternalFilesDir(null), video).getPath());
            view.setOnPreparedListener(mp -> mp.setLooping(true));
            FrameLayout root = new FrameLayout(this);
            root.setBackgroundColor(Color.BLACK);
            root.addView(view, new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT,
                    Gravity.CENTER));
            setContentView(root);
            view.start();
            return;
        }

        if (percent >= 100) {
            getWindow().getDecorView().setBackgroundColor(color);
            return;
        }
        Point size = new Point();
        getWindowManager().getDefaultDisplay().getRealSize(size);
        // Samma proportioner som skärmen, så sidorna skalas med roten ur ytandelen.
        double side = Math.sqrt(Math.max(1, percent) / 100.0);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        View patch = new View(this);
        patch.setBackgroundColor(color);
        root.addView(patch, new FrameLayout.LayoutParams(
                (int) Math.round(size.x * side), (int) Math.round(size.y * side), Gravity.CENTER));
        setContentView(root);
    }
}
