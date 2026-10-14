# Reads regexes and statements, one per line, separated by a line holding
# only "--"; prints, for each regex, a line of 1s and 0s.
use strict; use warnings;
binmode(STDIN, ':utf8'); binmode(STDOUT, ':utf8');
my (@rx, @st); my $in_st = 0;
while (my $line = <STDIN>) {
  chomp $line;
  if (!$in_st && $line eq '--') { $in_st = 1; next; }
  if ($in_st) { push @st, $line } else { push @rx, $line }
}
for my $r (@rx) {
  my $c = qr/$r/;
  print join('', map { $_ =~ $c ? '1' : '0' } @st), "\n";
}
