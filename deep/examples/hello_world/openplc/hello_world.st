PROGRAM hello_world
VAR
  cycle_timer : TON;
  timer_enable : BOOL := TRUE;
  cycle_count : DINT := 0;
  display_text : STRING := 'world';
END_VAR

cycle_timer(IN := timer_enable, PT := T#1s);

IF cycle_timer.Q THEN
  timer_enable := FALSE;
  cycle_count := cycle_count + 1;

  IF (cycle_count MOD 2) = 1 THEN
    display_text := 'hello';
  ELSE
    display_text := 'world';
  END_IF;
ELSE
  timer_enable := TRUE;
END_IF;
END_PROGRAM

CONFIGURATION Config0
RESOURCE Res0 ON PLC
TASK Main(INTERVAL := T#50ms, PRIORITY := 0);
PROGRAM MainInstance WITH Main : hello_world;
END_RESOURCE
END_CONFIGURATION
