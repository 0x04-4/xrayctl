# xrayctl

a small cli for xray and sing-box
pulls subscriptions, lists servers, connects and hides in the tray

## install

windows: run `install.cmd` and let it handle python, dependencies, the core and autostart

## use

```text
xrayctl
/list
/add <url>
/update
/connect 1
/status
/startup
/hide
```

regular commands work too: `xrayctl server list`, `xrayctl connect 1`

linux and macos work too, just without the tray and autostart
