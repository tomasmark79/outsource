# Get suggestions from the CLI without evaluating commands or configuration in the shell.
_outs_complete() {
    local candidate name
    COMPREPLY=()
    while IFS= read -r candidate; do
        COMPREPLY+=("$candidate")
    done < <(outs --complete "${COMP_WORDS[@]:1:COMP_CWORD}" 2>/dev/null)
    # Display names when listing alternatives; insert only IDs when completing.
    if [[ ${COMP_TYPE:-0} == 63 && ${COMP_WORDS[1]} == connect && $COMP_CWORD == 2 && ${#COMPREPLY[@]} -gt 1 ]]; then
        COMPREPLY=()
        while IFS=$'\t' read -r candidate name; do
            COMPREPLY+=("$candidate  $name")
        done < <(outs --complete-descriptions "${COMP_WORDS[@]:1:COMP_CWORD}" 2>/dev/null)
    fi
}
complete -F _outs_complete outs
