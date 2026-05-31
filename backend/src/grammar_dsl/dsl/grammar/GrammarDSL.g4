grammar GrammarDSL;

command
    : grammarCheckCmd EOF
    | generateExerciseCmd EOF
    | createQuizCmd EOF
    | submitAnswersCmd EOF
    | showResultsCmd EOF
    | showClassCmd EOF
    | showStudentsCmd EOF
    | showQuizCmd EOF
    | revisionPlanCmd EOF
    | historyCmd EOF
    | resetHistoryCmd EOF
    | spellCmd EOF
    | verbCmd EOF
    | synonymCmd EOF
    | helpCmd EOF
    ;

grammarCheckCmd
    : CHECK GRAMMAR paragraph
    ;

generateExerciseCmd
    : GENERATE quantitySpec? WITH featureExpr
    ;

quantitySpec
    : EXERCISE
    | count=NUMBER EXERCISES
    ;

createQuizCmd
    : CREATE QUIZ title=QUOTED_TEXT (WITH | GENERATE) count=NUMBER EXERCISES WITH featureExpr
    ;

submitAnswersCmd
    : SUBMIT ANSWERS FOR QUIZ quizId=NUMBER LEFT_BRACE answerEntry (answerSeparator answerEntry)* answerSeparator? RIGHT_BRACE
    ;

answerEntry
    : questionId=NUMBER EQUALS answerValue
    ;

answerSeparator
    : COMMA
    | SEMICOLON
    ;

answerValue
    : WORD
    | NUMBER
    | QUOTED_TEXT
    ;

showStudentsCmd
    : SHOW STUDENTS (FOR QUIZ quizId=NUMBER)? (WITH studentFilterExpr)?
    ;

showResultsCmd
    : SHOW RESULTS FOR STUDENT studentUsername=WORD (FOR QUIZ quizId=NUMBER)?
    ;

showQuizCmd
    : SHOW QUIZ quizId=NUMBER
    ;

showClassCmd
    : (SHOW STUDENTS FOR CLASS | SHOW CLASS) classId=NUMBER
    ;

studentFilterExpr
    : studentFilterOrExpr
    ;

studentFilterOrExpr
    : studentFilterAndExpr (OR studentFilterAndExpr)*
    ;

studentFilterAndExpr
    : studentFilterPrimary (AND studentFilterPrimary)*
    ;

studentFilterPrimary
    : LEFT_PAREN studentFilterExpr RIGHT_PAREN
    | comparisonExpr
    | statusExpr
    ;

comparisonExpr
    : SCORE op=(GT | GTE | LT | LTE | EQUALS) value=NUMBER
    | SCORE op=(GT | GTE | LT | LTE | EQUALS) value=PERCENTAGE
    ;

statusExpr
    : status=(SUBMITTED | NOT_SUBMITTED | PASSED | FAILED)
    ;

revisionPlanCmd
    : (SHOW)? REVISION PLAN
    ;

historyCmd
    : (SHOW)? HISTORY (limit=NUMBER)?
    ;

resetHistoryCmd
    : RESET HISTORY
    ;

spellCmd
    : SPELL word=WORD
    ;

verbCmd
    : VERB word=WORD
    ;

synonymCmd
    : SYNONYM word=WORD
    ;

helpCmd
    : HELP
    ;

featureExpr
    : featureOrExpr
    ;

featureOrExpr
    : featureAndExpr (OR featureAndExpr)*
    ;

featureAndExpr
    : featurePrimary (AND featurePrimary)*
    ;

featurePrimary
    : LEFT_PAREN featureExpr RIGHT_PAREN
    | featureAtom
    ;

featureAtom
    : (tense | aspect | voice | sentenceType | clauseStructure | grammaticalFeature)+
    ;

tense
    : PRESENT
    | PAST
    | FUTURE
    ;

aspect
    : SIMPLE
    | CONTINUOUS
    | PERFECT
    | PERFECT_CONTINUOUS
    ;

voice
    : ACTIVE
    | PASSIVE
    ;

sentenceType
    : DECLARATIVE
    | INTERROGATIVE
    | IMPERATIVE
    | EXCLAMATORY
    | AFFIRMATIVE
    | NEGATIVE
    ;

clauseStructure
    : SVO
    | SVC
    | SVA
    | SVOC
    | SVOO
    | RELATIVE_CLAUSE
    | CONDITIONAL
    ;

grammaticalFeature
    : ARTICLE
    | PREPOSITION
    | AGREEMENT
    ;

paragraph
    : (sentence)+
    ;

sentence
    : (sentencePart)+ sentenceTerminator?
    ;

sentencePart
    : WORD
    | NUMBER
    | COMMA
    | SEMICOLON
    | COLON
    | QUOTED_TEXT
    | PRESENT | PAST | FUTURE
    | SIMPLE | CONTINUOUS | PERFECT | PERFECT_CONTINUOUS
    | ACTIVE | PASSIVE
    | DECLARATIVE | IMPERATIVE | EXCLAMATORY
    | CHECK | GRAMMAR | SHOW | TOKENS | GENERATE | CREATE | QUIZ | SUBMIT | ANSWERS
    | WITH | FOR | AND | OR
    | SCORE | EXERCISE | EXERCISES | RELATIVE_CLAUSE | CONDITIONAL | ARTICLE | PREPOSITION | AGREEMENT | AFFIRMATIVE | NEGATIVE | INTERROGATIVE
    | SVO | SVC | SVA | SVOC | SVOO
    | SUBMITTED | NOT_SUBMITTED | PASSED | FAILED
    | REVISION | PLAN | HISTORY | RESET | VERB | SPELL | SYNONYM | RESULTS | STUDENT | STUDENTS | CLASS | HELP
    ;

sentenceTerminator
    : DOT
    | QUESTION_MARK
    | EXCLAMATION_MARK
    ;

// Lexer Rules
// Tenses
PRESENT         : [pP] [rR] [eE] [sS] [eE] [nN] [tT] ;
PAST            : [pP] [aA] [sS] [tT] ;
FUTURE          : [fF] [uU] [tT] [uU] [rR] [eE] ;

// Aspects
SIMPLE          : [sS] [iI] [mM] [pP] [lL] [eE] ;
CONTINUOUS      : [cC] [oO] [nN] [tT] [iI] [nN] [uU] [oO] [uU] [sS] ;
PERFECT         : [pP] [eE] [rR] [fF] [eE] [cC] [tT] ;

// Perfect Continuous (special case in lexer or parser)
PERFECT_CONTINUOUS : PERFECT WS CONTINUOUS ;

// Voices
ACTIVE          : [aA] [cC] [tT] [iI] [vV] [eE] ;
PASSIVE         : [pP] [aA] [sS] [sS] [iI] [vV] [eE] ;

// Sentence Types
DECLARATIVE     : [dD] [eE] [cC] [lL] [aA] [rR] [aA] [tT] [iI] [vV] [eE] ;
IMPERATIVE      : [iI] [mM] [pP] [eE] [rR] [aA] [tT] [iI] [vV] [eE] ;
EXCLAMATORY     : [eE] [xX] [cC] [lL] [aA] [mM] [aA] [tT] [oO] [rR] [yY] ;

// Command Keywords
CHECK           : [cC] [hH] [eE] [cC] [kK] ;
GRAMMAR         : [gG] [rR] [aA] [mM] [mM] [aA] [rR] ;
SHOW            : [sS] [hH] [oO] [wW] ;
TOKENS          : [tT] [oO] [kK] [eE] [nN] [sS] ;
GENERATE        : [gG] [eE] [nN] [eE] [rR] [aA] [tT] [eE] ;
CREATE          : [cC] [rR] [eE] [aA] [tT] [eE] ;
QUIZ            : [qQ] [uU] [iI] [zZ] ;
SUBMIT          : [sS] [uU] [bB] [mM] [iI] [tT] ;
ANSWERS         : [aA] [nN] [sS] [wW] [eE] [rR] [sS] ;

// Connectives
WITH            : [wW] [iI] [tT] [hH] ;
FOR             : [fF] [oO] [rR] ;
AND             : [aA] [nN] [dD] ;
OR              : [oO] [rR] ;

// Grammar components
SCORE           : [sS] [cC] [oO] [rR] [eE] ;
EXERCISE        : [eE] [xX] [eE] [rR] [cC] [iI] [sS] [eE] ;
EXERCISES       : [eE] [xX] [eE] [rR] [cC] [iI] [sS] [eE] [sS] ;
RELATIVE_CLAUSE : [rR] [eE] [lL] [aA] [tT] [iI] [vV] [eE] WS [cC] [lL] [aA] [uU] [sS] [eE] ;
CONDITIONAL     : [cC] [oO] [nN] [dD] [iI] [tT] [iI] [oO] [nN] [aA] [lL] ;
ARTICLE         : [aA] [rR] [tT] [iI] [cC] [lL] [eE] ;
PREPOSITION     : [pP] [rR] [eE] [pP] [oO] [sS] [iI] [tT] [iI] [oO] [nN] ;
AGREEMENT       : [aA] [gG] [rR] [eE] [eE] [mM] [eE] [nN] [tT] ;
AFFIRMATIVE     : [aA] [fF] [fF] [iI] [rR] [mM] [aA] [tT] [iI] [vV] [eE] ;
NEGATIVE        : [nN] [eE] [gG] [aA] [tT] [iI] [vV] [eE] ;
INTERROGATIVE   : [iI] [nN] [tT] [eE] [rR] [rR] [oO] [gG] [aA] [tT] [iI] [vV] [eE] ;
SVO             : [sS] [vV] [oO] ;
SVC             : [sS] [vV] [cC] ;
SVA             : [sS] [vV] [aA] ;
SVOC            : [sS] [vV] [oO] [cC] ;
SVOO            : [sS] [vV] [oO] [oO] ;
SUBMITTED       : [sS] [uU] [bB] [mM] [iI] [tT] [tT] [eE] [dD] ;
NOT_SUBMITTED   : [nN] [oO] [tT] WS [sS] [uU] [bB] [mM] [iI] [tT] [tT] [eE] [dD] ;
PASSED          : [pP] [aA] [sS] [sS] [eE] [dD] ;
FAILED          : [fF] [aA] [iI] [lL] [eE] [dD] ;
REVISION        : [rR] [eE] [vV] [iI] [sS] [iI] [oO] [nN] ;
PLAN            : [pP] [lL] [aA] [nN] ;
HISTORY         : [hH] [iI] [sS] [tT] [oO] [rR] [yY] ;
RESET           : [rR] [eE] [sS] [eE] [tT] ;
VERB            : [vV] [eE] [rR] [bB] ;
SPELL           : [sS] [pP] [eE] [lL] [lL] ;
SYNONYM         : [sS] [yY] [nN] [oO] [nN] [yY] [mM] ;
RESULTS         : [rR] [eE] [sS] [uU] [lL] [tT] [sS] ;
STUDENT         : [sS] [tT] [uU] [dD] [eE] [nN] [tT] ;
STUDENTS        : [sS] [tT] [uU] [dD] [eE] [nN] [tT] [sS] ;
CLASS           : [cC] [lL] [aA] [sS] [sS] ;
HELP            : [hH] [eE] [lL] [pP] ;

GTE             : '>=' ;
LTE             : '<=' ;
GT              : '>' ;
LT              : '<' ;
EQUALS          : '=' ;

LEFT_PAREN      : '(' ;
RIGHT_PAREN     : ')' ;
LEFT_BRACE      : '{' ;
RIGHT_BRACE     : '}' ;
COMMA           : ',' ;
SEMICOLON       : ';' ;
COLON           : ':' ;
DOT             : '.' ;
QUESTION_MARK   : '?' ;
EXCLAMATION_MARK: '!' ;

PERCENTAGE      : [0-9]+ '%' ;
NUMBER          : [0-9]+ ;
WORD            : LETTER (LETTER | WORD_APOSTROPHE)* ;
QUOTED_TEXT     : '"' (~["])* '"' ;

WS              : [ \t\r\n\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000]+ -> skip ;

fragment LETTER : [a-zA-Z0-9_] ;
fragment WORD_APOSTROPHE : '\'' | '\u2018' | '\u2019' ;
