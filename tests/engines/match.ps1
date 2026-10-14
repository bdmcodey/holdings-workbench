# Reads {"regexes": [...], "statements": [...]} as JSON on stdin; writes, for
# each regex, a string of 1s and 0s: whether it matches each statement.
# .NET's own engine, as C#, PowerShell and MarcEdit use it. The loop is C#
# because a PowerShell loop over every pair takes minutes.
[Console]::InputEncoding = [Text.Encoding]::UTF8
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -TypeDefinition @"
using System.Text;
using System.Text.RegularExpressions;
public static class WorkbenchMatch {
  public static string[] Run(string[] regexes, string[] statements) {
    var outp = new string[regexes.Length];
    for (int i = 0; i < regexes.Length; i++) {
      var rx = new Regex(regexes[i]);
      var sb = new StringBuilder(statements.Length);
      foreach (var s in statements) sb.Append(rx.IsMatch(s) ? '1' : '0');
      outp[i] = sb.ToString();
    }
    return outp;
  }
}
"@
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$result = [WorkbenchMatch]::Run([string[]]$data.regexes, [string[]]$data.statements)
ConvertTo-Json -InputObject @($result) -Compress
