PROGRAM MainProgram
VAR
  hello : STRING := 'hello';
  world : STRING := 'world';
  hello_world : STRING := '';
  world_latch : BOOL := FALSE;
  hello_TON : TON;
  world_TON : TON;
END_VAR

hello_TON(IN := NOT world_latch, PT := T#1s);
IF hello_TON.Q THEN
  world_latch := TRUE;
END_IF;

world_TON(IN := world_latch, PT := T#1s);
IF world_TON.Q THEN
  world_latch := FALSE;
END_IF;

IF NOT world_latch THEN
  hello_world := hello;
ELSE
  hello_world := world;
END_IF;
END_PROGRAM

CONFIGURATION Config0
RESOURCE Res0 ON PLC
TASK Main(INTERVAL := T#100ms, PRIORITY := 0);
PROGRAM MainInstance WITH Main : MainProgram;
END_RESOURCE
END_CONFIGURATION
