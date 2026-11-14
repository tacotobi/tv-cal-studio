package se.tvcal.pqprobe;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Point;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;

/**
 * Enfärgad helskärm, eller en centrerad ruta mot svart, som mätaren kan läsa av.
 *
 * am start -n se.tvcal.pqprobe/.PatternActivity [--es color ffffff] [--ei window 10]
 * window = rutans andel av skärmytan i procent. Utelämnad eller 100 ger helskärm.
 */
public class PatternActivity extends Activity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        String hex = getIntent().getStringExtra("color");
        int color = Color.parseColor("#" + (hex == null ? "ffffff" : hex));
        int percent = getIntent().getIntExtra("window", 100);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

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
