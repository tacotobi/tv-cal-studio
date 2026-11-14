package se.tvcal.pqprobe;

import android.app.Activity;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;

import java.io.File;
import java.io.FileWriter;

/**
 * Läser MediaTeks bilddatabas och skriver resultatet till en fil som adb kan hämta.
 * Innehåller ingen skrivkod – provet ska inte kunna ändra något på TV:n.
 *
 * am start -n se.tvcal.pqprobe/.ProbeActivity --es paths general,source \
 *     [--es selection "..."] [--es args "a,b"] [--es projection "x,y"]
 */
public class ProbeActivity extends Activity {
    private static final String TAG = "PQPROBE";
    private static final String BASE = "content://com.mediatek.tv.settingspqdb/";
    private static final int MAX_ROWS = 2000;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        StringBuilder out = new StringBuilder();
        String paths = getIntent().getStringExtra("paths");
        String selection = getIntent().getStringExtra("selection");
        String[] args = split(getIntent().getStringExtra("args"));
        String[] projection = split(getIntent().getStringExtra("projection"));

        for (String path : (paths == null ? "general" : paths).split(",")) {
            out.append("### ").append(path).append('\n');
            try (Cursor c = getContentResolver().query(
                    Uri.parse(BASE + path), projection, selection, args, null)) {
                dump(c, out);
            } catch (Throwable t) {
                out.append("FEL: ").append(t).append('\n');
            }
        }

        // "general" svarar bara på första namnet i projektionen, så varje nyckel frågas för sig.
        String[] keys = split(getIntent().getStringExtra("keys"));
        if (keys != null) {
            out.append("### general per nyckel\n");
            for (String key : keys) {
                out.append(key).append('=');
                try (Cursor c = getContentResolver().query(
                        Uri.parse(BASE + "general"), new String[] {key}, null, null, null)) {
                    out.append(c != null && c.moveToFirst() ? c.getString(0) : "<saknas>");
                } catch (Throwable t) {
                    out.append("FEL: ").append(t);
                }
                out.append('\n');
            }
        }

        File file = new File(getExternalFilesDir(null), "out.txt");
        try (FileWriter w = new FileWriter(file)) {
            w.write(out.toString());
            Log.i(TAG, "skrev " + out.length() + " tecken till " + file);
        } catch (Throwable t) {
            Log.e(TAG, "kunde inte skriva " + file, t);
        }
        finish();
    }

    private static void dump(Cursor c, StringBuilder out) {
        if (c == null) {
            out.append("null\n");
            return;
        }
        out.append("rader=").append(c.getCount())
           .append(" kolumner=").append(String.join("|", c.getColumnNames())).append('\n');
        int n = 0;
        while (c.moveToNext() && n++ < MAX_ROWS) {
            for (int i = 0; i < c.getColumnCount(); i++) {
                if (i > 0) out.append('|');
                try {
                    out.append(c.getString(i));
                } catch (Throwable t) {
                    out.append("<blob>");
                }
            }
            out.append('\n');
        }
    }

    private static String[] split(String s) {
        return s == null ? null : s.split(",");
    }
}
