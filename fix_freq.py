import re

with open("/home/idona/MoStar/IdimIkang-main-1/observer_bundle/test_ft_bridge.py", "r+") as f:
    c = f.read()
    c = c.replace("15T", "15min").replace("1H", "1h").replace("1D", "1d")
    f.seek(0)
    f.write(c)
    f.truncate()

print("done")
