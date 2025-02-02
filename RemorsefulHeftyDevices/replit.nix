{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.python-telegram-bot
  ];
}
