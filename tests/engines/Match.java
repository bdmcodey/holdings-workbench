// Reads regexes and statements, one per line, separated by a line holding
// only "--"; prints, for each regex, a line of 1s and 0s. A regex starting
// "alma:" is Alma rule text: unescaped as a quoted string, then matched the
// way a Drools "matches" does, against the whole value.
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.Pattern;

public class Match {
  public static void main(String[] args) throws IOException {
    BufferedReader in = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));
    List<String> rx = new ArrayList<>(), st = new ArrayList<>();
    boolean inSt = false;
    for (String line; (line = in.readLine()) != null; ) {
      if (!inSt && line.equals("--")) { inSt = true; continue; }
      (inSt ? st : rx).add(line);
    }
    PrintStream out = new PrintStream(System.out, true, "UTF-8");
    for (String r : rx) {
      boolean alma = r.startsWith("alma:");
      String text = alma ? unquote(r.substring(5)) : r;
      Pattern p = Pattern.compile(text);
      StringBuilder sb = new StringBuilder();
      for (String s : st) {
        boolean hit = alma ? s.matches(text) : p.matcher(s).find();
        sb.append(hit ? '1' : '0');
      }
      out.println(sb);
    }
  }

  // The body of a quoted string, as a rule's parser reads it.
  static String unquote(String s) {
    StringBuilder sb = new StringBuilder();
    for (int i = 0; i < s.length(); i++) {
      char c = s.charAt(i);
      if (c == '\\' && i + 1 < s.length()) { sb.append(s.charAt(++i)); }
      else if (c == '"') { throw new IllegalArgumentException("bare quote"); }
      else { sb.append(c); }
    }
    return sb.toString();
  }
}
