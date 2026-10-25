# Návrhy získáváme z CLI; příkazy ani obsah konfigurace nevyhodnocujeme v shellu.
_outs_complete() {
    local candidate
    COMPREPLY=()
    while IFS= read -r candidate; do
        COMPREPLY+=("$candidate")
    done < <(outs --complete "${COMP_WORDS[@]:1:COMP_CWORD}" 2>/dev/null)
}
complete -F _outs_complete outs
