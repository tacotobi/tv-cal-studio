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
 * Bara nycklarna i WRITABLE går att skriva – provet ska inte kunna ändra något annat på TV:n.
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

    /**
     * Nycklar som provet får skriva, med tillåtet intervall. Gain antas vara 11 bitar med 1024
     * som 1,0 (förinställningarna ligger på 855–1060); golvet 512 räcker för att se skalan och
     * håller kanalen synlig.
     */
    private static final java.util.Map<String, int[]> WRITABLE = new java.util.HashMap<>();
    static {
        WRITABLE.put("Backlight", new int[] {0, 100});
        for (String c : new String[] {"Red", "Green", "Blue"}) {
            WRITABLE.put("Color_Temperature_" + c + "_Gain", new int[] {512, 2047});
            WRITABLE.put("Color_Temperature_Warm_" + c + "_Gain", new int[] {512, 2047});
            // Offset: HAL:en får 1024 som noll fast nycklarna är tomma i databasen.
            WRITABLE.put("Color_Temperature_" + c + "_Offset", new int[] {512, 1536});
            WRITABLE.put("Color_Temperature_Warm_" + c + "_Offset", new int[] {512, 1536});
            // Flerpunkts vitbalans: tolv punkter, 50 är neutralt.
            for (int i = 0; i < 12; i++) {
                WRITABLE.put("PQ_WB_11_Point_" + i + "_" + c, new int[] {0, 100});
            }
        }
        // Färghantering: nyans, mättnad och ljus per färg (R, G, B, cyan, magenta, gul, hud),
        // samt RGB-gain och -offset. Alla står på 50 från början.
        for (String a : new String[] {"H", "S", "Y"}) {
            for (String f : new String[] {"R", "G", "B", "C", "M", "Y", "F"}) {
                WRITABLE.put("COLORTUNER_" + a + "_" + f, new int[] {0, 100});
            }
        }
        for (String c : new String[] {"R", "G", "B"}) {
            WRITABLE.put("COLORTUNER_" + c + "_GAIN", new int[] {0, 100});
            WRITABLE.put("COLORTUNER_" + c + "_OFFSET", new int[] {0, 100});
        }
    }

    /** Textnycklar som provet får skriva, med tillåtna värden. */
    private static final java.util.Map<String, java.util.List<String>> WRITABLE_TEXT =
            new java.util.HashMap<>();
    static {
        WRITABLE_TEXT.put("Color_Temperature", java.util.Arrays.asList("Warm", "Standard", "Cool"));
        WRITABLE_TEXT.put("PQ_WB_11_Point_enabled", java.util.Arrays.asList("On", "Off"));
        WRITABLE_TEXT.put("COLORTUNER_SWITCH", java.util.Arrays.asList("On", "Off"));
        // Värdena finns som strängar i TvAgentService; vilka som når panelen är oprovat.
        WRITABLE_TEXT.put("Color_space", java.util.Arrays.asList(
                "Auto", "BT709", "DCI", "DCI_P3", "BT2020", "Native", "Wide", "Standard"));
        WRITABLE_TEXT.put("Gamut_Mapping", java.util.Arrays.asList("Enable", "Disable"));
        java.util.List<String> gammas = java.util.Arrays.asList(
                "Gamma18", "Gamma20", "Gamma22", "Gamma24", "Gamma26");   // BT1886 lagras men når aldrig HAL:en
        WRITABLE_TEXT.put("Gamma", gammas);
        WRITABLE_TEXT.put("Gamma_Mode", gammas);
    }

    /** Leverantören tar en nyckel per anrop: nyckelnamnet som kolumn, värdet som sträng. */
    private int write(String assignment) {
        String[] kv = assignment.split("=", 2);
        if (kv.length != 2) {
            throw new IllegalArgumentException("formatet är <nyckel>=<värde>");
        }
        String value;
        int[] range = WRITABLE.get(kv[0]);
        java.util.List<String> allowed = WRITABLE_TEXT.get(kv[0]);
        if (range != null && kv[1].isEmpty() && kv[0].endsWith("_Offset")) {
            value = "";   // offset-nycklarna är tomma från början, så tomt måste gå att återställa
        } else if (range != null) {
            int n = Integer.parseInt(kv[1]);
            if (n < range[0] || n > range[1]) {
                throw new IllegalArgumentException(kv[0] + " ska vara " + range[0] + "-" + range[1]);
            }
            value = String.valueOf(n);
        } else if (allowed != null) {
            if (!allowed.contains(kv[1])) {
                throw new IllegalArgumentException(kv[0] + " ska vara en av " + allowed);
            }
            value = kv[1];
        } else {
            throw new IllegalArgumentException(
                    "tillåtna nycklar: " + WRITABLE.keySet() + " " + WRITABLE_TEXT.keySet());
        }
        ContentValues values = new ContentValues();
        values.put(kv[0], value);
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
