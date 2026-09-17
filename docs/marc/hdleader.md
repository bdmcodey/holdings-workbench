# MARC 21 Leader

> **Reference copy.** Not written by this project. Text extracted verbatim from
> the Library of Congress documentation so that decisions about the converter
> can cite the standard rather than recollection of it.
>
> | | |
> |---|---|
> | Source | <https://www.loc.gov/marc/holdings/hdleader.html> |
> | Edition | MARC 21 Holdings |
> | Retrieved | 17 September 2026 |
> | Extracted with | `scripts/extract_marc_doc.py` (pypdf) |
> | Authority | Network Development and MARC Standards Office, Library of Congress |
>
> The body below is the extraction unedited, page markers included, inside a
> code fence. Fenced deliberately: the text uses `#` for the blank indicator
> value and `$a` for subfield codes, and Markdown would eat both. Nothing is
> reworded, reordered or summarised -- a paraphrase of a standard is no longer
> the standard, and this file exists to be quotable.
>
> Extraction is imperfect where the original used tables or two columns; where
> a passage looks garbled, the source URL above is the authority, not this
> file. If LC revises the page, re-run the script rather than patching this
> file, and update the edition and retrieval date.

```text
===== PAGE 1 =====
Library of Congress >> MARC >> Holdings >> Leader
Leader (NR)
MARC 21 Holdings October 2001
Indicators and Subfield Codes
No indicators or subfield codes; the data elements are positionally defined.
Character Positions
00-04 - Record length
05 - Record status
c - Corrected or revised
d - Deleted
n - New
06 - Type of record
u - Unknown
v - Multipart item holdings
x - Single-part item holdings
y - Serial item holdings
07-08 - Undefined character positions
# - Undefined
09 - Character coding scheme
# - MARC-8
a - UCS/Unicode
10 - Indicator count
2 - Number of character positions used for
indicators
11 - Subfield code length
2 - Number of character positions used for a
subfield code
12-16 - Base address of data
[number] - Length of Leader and Directory
17 - Encoding level
1 - Holdings level 1
2 - Holdings level 2
3 - Holdings level 3
4 - Holdings level 4
5 - Holdings level 4 with piece designation
m - Mixed level
u - Unknown
z - Other level
18 - Item information in record
i - Item information
n - No item information
19 - Undefined character position
# - Undefined
20 - Length of the length-of-field portion
4 - Number of characters in the length-of-field
portion of a Directory entry
21 - Length of the starting-character-position
portion
5 - Number of characters in the starting-character-
position portion of a Directory entry
22 - Length of the implementation-defined
portion
0 - Number of characters in the implementation-
defined portion of a Directory entry
23 - Undefined
0 - Undefined
FIELD DEFINITION AND SCOPE
First field of a separate holdings record. It is fixed in length at 24 character positions (00-23).
The Leader consists of data elements that contain numbers or coded values that define the
parameters for the processing of the record in an automated system.
Character positions 20-23 comprise the Entry map for the Directory. They contain four one-
character numbers that specify the structure of the entries in the Directory. More detailed

===== PAGE 2 =====
information about the structure of the Leader is contained in MARC 21 Specifications for
Record Structure, Character Sets, and Exchange Media.
GUIDELINES FOR APPLYING CONTENT DESIGNATORS
■ CHARACTER POSITIONS
00-04 - Record length
Computer-generated, five-character number equal to the length of the entire record, including
itself and the record terminator. The number is right justified and each unused position contains
a zero.
05 - Record status
Relationship of the record to a file.
Used for file maintenance purposes.
c - Corrected or revised
Addition or change has been made to the record.
d - Deleted
Record has been deleted.
n - New
Record is a newly input record.
06 - Type of record
Characteristics and definitions of the components of the record. When holdings information is
embedded in a MARC bibliographic record, the Leader/06 code may be contained in field 841
$a (Holdings Coded Data Values, Type of record).
u - Unknown
Record is a holdings record, but its type of holdings is unspecified.
v - Multipart item holdings
Holdings statement is for a nonserial bibliographic item that is composed of more than
one physical part but is complete in a finite number of separate physical parts, such as a
multivolume monograph, a kit, a music score and parts, a monograph with a multipart
supplement.
x - Single-part item holdings
Holdings statement is for a bibliographic item that is complete in a single physical part,
for example, a one-volume book, a single-part component of a kit.
y - Serial item holdings
Holdings statement is for a serial bibliographic item (that is, one issued in successive parts
and intended to be continued indefinitely).
07-08 - Undefined character positions
Both are undefined; each contains a blank (#).

===== PAGE 3 =====
When holdings information is embedded in a MARC bibliographic record, these two blanks
and the Leader/06 code are contained in subfield $a (Type of record) of field 841 (Holdings
Coded Data Values), which is also embedded in the bibliographic record.
09 - Character coding scheme
Character coding scheme used in the record.
Coding scheme used affects the number of octets needed per character, the placement of non-
spacing characters, and the use of escape sequences and may affect the character repertoire.
Detailed information on the character sets used in MARC 21 records is contained in MARC 21
Specifications for Record Structure, Character Sets, and Exchange Media.
# - MARC-8
Character coding in the record uses the 8-bit character sets described in MARC 21
Specifications for Record Structure, Character Sets, and Exchange Media. Non-default
character sets used are identified in field 066.
a - UCS/Unicode
Code a indicates that the character coding in the record makes use of characters from the
Universal Coded Character Set (UCS) (ISO 10646), or Unicode™, an industry subset.
When holdings information is embedded in a MARC bibliographic record, the Leader/09
code may be contained in subfield $a (Type of record) of field 841 (Holdings Coded Data
Values), which is also embedded in the bibliographic record.
10 - Indicator count
Computer-generated number 2 that indicates the number of indicators occurring in each
variable data field.
(An indicator character position contains a code which conveys information that interprets or
supplements the data found in the field.) In MARC 21, two character positions at the beginning
of each variable data field are reserved for indicators; therefore, the Indicator count is always 2.
2 - Number of character positions used for indicators
11 - Subfield code length
Computer-generated number 2 that indicates the number of character positions used for each
subfield code in a variable data field.
(Each data element in a variable data field is identified by a subfield code.) In MARC 21, a
subfield code consists of a delimiter ($) and a lowercase alphabetic or numeric data element
identifier; therefore, the Subfield code count is always 2.
2 - Number of character positions used for a subfield code
12-16 - Base address of data
Computer-generated, five-character numeric string that specifies the first character position of
the first variable control field in a record. The number is right justified and each unused
position contains a zero.

===== PAGE 4 =====
Number is the base from which the starting character position of all the other fields in the
record is addressed in the Directory. (The starting character position in the Directory entry for
each field of the record is relative to the first character of the first variable control field rather
than the beginning of the record.) The Base address of data is equal to the sum of the lengths of
the Leader and the Directory, including the field terminator character at the end of the
Directory.
[number] - Length of Leader and Directory
17 - Encoding level
Level-of-specificity of the holdings statement. Codes 1, 2, 3, and 4 reflect the requirements of
Levels 1, 2, 3, and 4 of Holdings Statements for Bibliographic Items (ANSI/NISO Z39.71)
(formerly Serial Holdings Statements (ANSI/NISO Z39.44)) and Holdings Statements for Non-
Serial Items (ANSI/NISO Z39.57)) and codes 1, 2, and 3 reflect the requirements of Levels 1,
2, and 3 of Holdings Statements-Summary Level (ISO 10324). The MARC content designators
given in the description of each holdings level are the ones required by Z39.71. Optional data
elements for each level are not mentioned here; they are given in each standard. A single-part
item holdings statement is normally recorded at level 1. A multipart or serial item holdings
statement may be recorded at any level.
When holdings information is embedded in a MARC bibliographic record, this information
may be contained in field 841 (Holdings Coded Data Values), subfield $e (Encoding level),
which is also embedded in the bibliographic record.
1 - Holdings level 1
Holdings statement is formulated according to level 1 of the applicable standard.
Minimally, it consists of an item identifier for the bibliographic item for which holdings
are recorded and a location identifier.
Item identifier may be contained in one of the following fields:
004 Control Number for Related Bibliographic Record
010 Library of Congress Control Number
014 Linkage Number
020 International Standard Book Number
022 International Standard Serial Number
024 Other Standard Identifier
027 Standard Technical Report Number
030 CODEN Designation
Location identifier is contained in subfield $a (Location) of field 852 (Location).
Leader/17 1
004 ###86104385#
852 ##$aCSf$bSpCol
2 - Holdings level 2
Holdings statement is formulated according to level 2 of the applicable standard.
Minimally, in addition to the requirements for level 1, it includes a code in each of the
following 008 (Fixed-Length Data Elements) and, when appropriate, 007 (Physical
Description Fixed Field) character positions:

===== PAGE 5 =====
008/06 2
[Receipt or acquisition status 007/00 Category of material]
008/12 4
[General retention policy 007/01 Specific material designation]
008/16 8
[Completeness]
008/26-31 891017
[Date of report]
007/00 a
[Category of material]
007/01 d
[Specific material designation]
Leader/17 2
004 ###86104385#
[Control number for related bibliographic record]
008/06 4
[Code indicating item is currently received]
008/12 8
[Code indicating holdings are permanently retained]
008/16 2
[Code indicating reporting organization holds an incomplete
published run of the item]
008/26-31 891017
[Date of the holdings report]
852 ##$aCSf$bSpCol
3 - Holdings level 3
Holdings statement is formulated according to level 3 of the applicable standard.
Minimally, in addition to the requirements for level 2, it includes summary holdings
information, that is, holdings at the first level of enumeration and chronology, in one or
more of the following holdings data fields:
853 Captions and Pattern-Basic Bibliographic Unit
863 Enumeration and Chronology-Basic Bibliographic Unit
866 Textual Holdings-Basic Bibliographic Unit
854 Captions and Pattern-Supplementary Material
864 Enumeration and Chronology-Supplementary Material
867 Textual Holdings-Supplementary Material
855 Captions and Pattern-Indexes
865 Enumeration and Chronology-Indexes
868 Textual Holdings-Indexes
Leader/17 3
004 ###86104385#
[Code number for related bibliographic record]
008/06 4
[Code indicating item is currently received]

===== PAGE 6 =====
008/12 8
[Code indicating holdings are permanently retained]
008/16 2
[Code indicating reporting organization holds an incomplete
published run of the item]
008/26-31 891017
[Date of the holdings report]
852 ##$aCSf$bSpCol
853 00$81$ano.$i(year)$j(month)
863 30$81.1$a180-242$i1976-1983
4 - Holdings level 4
Holdings statement is formulated according to level 4 of the applicable standard.
Minimally, in addition to the requirements for level 2, it includes detailed holdings
information, that is, the first and all subsequent levels of enumeration and chronology in
either itemized or compressed form or a combination of the two, in one or more of the
853-855 Captions and Pattern, 863-865 Enumeration and Chronology, and 866-868
Textual Holdings fields.
Leader/17 4
004 ###86104385#
[Code number for related bibliographic record]
008/06 4
[Code indicating item is currently received]
008/12 8
[Code indicating holdings are permanently retained]
008/16 2
[Code indicating reporting organization holds an incomplete
published run of the item]
008/26-31 891017
[Date of the holdings report]
852 ##$aCSf$bSpCol
853 00$81$ano.$i(year)$j(month)
863 40$81.1$a180-226$i1976-1981
863 44$81.2$a222
863 40$81.3$a230$i1982$jApril
863 40$81.4$a235$i1982$jDec.
863 40$81.5$a237$i1983$jMar.
863 40$81.6$a239-242$i1983$jJune-Oct.
[Multiple 863 fields contain detailed holdings statements for an
incomplete published run of the item.]
5 - Holdings level 4 with piece designation
Holdings statement includes physical piece designation that is contained in subfield $p
(Piece designation) of field 852 (Location, one of the 863-865 Enumeration and
Chronology fields, or an 876-878 Item Information field, or in subfield $a (Textual
holdings) in one of the 866-868 Textual Holdings fields.
m - Mixed level
Holdings are recorded at more than one level, for example, when the levels for
retrospective and current holdings differ. The value in the first indicator position (Field

===== PAGE 7 =====
encoding level) of the applicable 863-865 Enumeration and Chronology and 866-868
Textual Holdings fields indicate the level for each holdings data field.
u - Unknown
z - Other level
Holdings statement does not meet any of the levels of specificity defined by the other
codes.
18 - Item information in record
Whether item information is in the record, contained in one or more occurrences of fields 876-
878 (Item Information fields).
i - Item information
Item information is in the record, contained in fields 876-878.
Leader/18 i
[Code indicating that item information is in record]
852 8#$aTxAM$bTexas Documents$hUA242.7$iEn89
876 ##$aAAH8128-2-1$c12.00$pA14812385910$qA14821385083$xRe-
catalog as added copy for stacks when checked in.
n - No item information
19 - Undefined character position
Undefined and contains a blank (#).
20 - Length of the length-of-field portion
Always a 4.
4 - Number of characters in the length-of-field portion of a Directory entry
21 - Length of the starting-character-position portion
Always a 5.
5 - Number of characters in the starting-character-position portion of a Directory entry
22 - Length of the implementation-defined portion
In MARC 21, a Directory entry does not contain an implementation-defined portion.
Always a 0.
0 - Number of characters in the implementation-defined portion of a Directory entry
23 - Undefined
Undefined; always contains a 0.
INPUT CONVENTIONS

===== PAGE 8 =====
System-Generated Elements - The following Leader elements are usually system generated:
00-04 Logical record length
07-08 Undefined character positions
09 Character coding scheme
10 Indicator count
11 Subfield code count
12-16 Base address of data
19 Undefined character position
20-23 Entry map
It is common for default values in other Leader elements to be generated automatically as well.
Capitalization - Alphabetic codes are input as lower case letters.
CONTENT DESIGNATOR HISTORY
06 - Type of record
v - Multipart Item Holdings [NEW, 1991]
Code v was added to distinguish multipart item holdings from serial item holdings. Prior to that change, both multipart and serial items
were contained in code y.
18 - Item information in record [NEW, 1994]
# - Undefined [OBSOLETE, 1994]
Library of Congress >> MARC >> Holdings >> Leader
(03/08/2008) Contact Us
```
