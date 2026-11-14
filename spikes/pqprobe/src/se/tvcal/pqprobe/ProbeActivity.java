package se.tvcal.pqprobe;

import android.app.Activity;
import android.content.ContentValues;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;

import java.io.File;
import java.io.FileWriter;

/**
 * Läser MediaTeks bilddatabas och skriver resultatet till en fil som adb kan hämta.
 * Enda skrivningen som går igenom är Backlight – provet ska inte kunna ändra något annat på TV:n.
 *
 * am start -n se.tvcal.pqprobe/.ProbeActivity --es paths general,source \
 *     [--es selection "..."] [--es args "a,b"] [--es projection "x,y"]
 *     [--es keys "Backlight,Contrast"] [--es set "Backlight=29"]
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

        String set = getIntent().getStringExtra("set");
        if (set != null) {
            out.append("### skrivning ").append(set).append('\n');
            try {
                out.append("update=").append(write(set)).append('\n');
                // Leverantören svarar direkt och lagrar värdet på en egen tråd,
                // så läsningen nedan måste vänta för att se det nya värdet.
                Thread.sleep(1500);
            } catch (Throwable t) {
                out.append("FEL: ").append(t).append('\n');
            }
        }

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

    /** Leverantören tar en nyckel per anrop: nyckelnamnet som kolumn, värdet som sträng. */
    private int write(String assignment) {
        String[] kv = assignment.split("=", 2);
        if (kv.length != 2 || !"Backlight".equals(kv[0])) {
            throw new IllegalArgumentException("bara Backlight=<0-100> är tillåtet");
        }
        int value = Integer.parseInt(kv[1]);
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("värdet ska vara 0-100");
        }
        ContentValues values = new ContentValues();
        values.put(kv[0], String.valueOf(value));
        return getContentResolver().update(Uri.parse(BASE + "general"), values, null, null);
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
