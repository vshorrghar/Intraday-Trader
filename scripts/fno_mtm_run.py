from fno.monitor import update_all_open_strategies

for p in ["vishal-live", "vishal", "neha"]:
    result = update_all_open_strategies(p)
    print(f"{p}: {result}")
