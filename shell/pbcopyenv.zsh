# pbcopyenv NAME: append NAME=<clipboard> to ./.env (created if missing, private to you).
# zsh on macOS (pbpaste). The secret is never printed, so it stays out of an agent's conversation.
# Install: echo "source $PWD/shell/pbcopyenv.zsh" >> ~/.zshrc   (run from the clone)
# In a Claude Code session: ! pbcopyenv MY_SUPER_TOKEN_NAME
pbcopyenv() {
  if [[ $# -ne 1 || ! "$1" =~ '^[A-Za-z_][A-Za-z0-9_]*$' ]]; then
    print -u2 "usage: pbcopyenv VARIABLE_NAME"
    return 2
  fi
  local name=$1 value file=.env
  value=$(pbpaste) || return 1
  if [[ -z "$value" ]]; then
    print -u2 "pbcopyenv: clipboard is empty"
    return 1
  fi
  if [[ "$value" == *$'\n'* ]]; then
    print -u2 "pbcopyenv: clipboard holds several lines, not written"
    return 1
  fi
  if [[ ! -e $file ]]; then
    (umask 077; : > $file) || return 1
  elif grep -q "^${name}=" $file; then
    print -u2 "pbcopyenv: $name is already in $file, appending anyway (the last line usually wins)"
  fi
  # Start on a fresh line when the file does not end with a newline.
  [[ -s $file && -n "$(tail -c 1 $file)" ]] && print >> $file
  print -r -- "${name}=${value}" >> $file
  print "pbcopyenv: added $name to ${PWD}/$file"
}
