# TVL Constraint Check Demo
# Shows structural constraint validation and SAT checking

Output output/constraint-check.gif
Source tapes/_theme.tape

Hide
Type "clear"
Enter
Show

Sleep 1s

# Introduction
Type "# TVL Structural Constraint Checking"
Enter
Sleep 2s

# Show a spec with constraints
Type "cat << 'EOF'"
Enter
Type "tvars:"
Enter
Type "  - name: model"
Enter
Type "    type: enum[str]"
Enter
Type "    domain: ['gpt-4', 'claude-3']"
Enter
Type "  - name: use_cot"
Enter
Type "    type: bool"
Enter
Type "    domain: [true, false]"
Enter
Type "  - name: temperature"
Enter
Type "    type: float"
Enter
Type "    domain: { range: [0.0, 2.0] }"
Enter
Enter
Type "constraints:"
Enter
Type "  structural:"
Enter
Type "    - when: 'use_cot = true'"
Enter
Type "      then: 'temperature <= 0.5'"
Enter
Type "EOF"
Enter
Sleep 3s

# Check constraint satisfiability
Type "# Check if constraints are satisfiable..."
Enter
Sleep 1.5s

Type "tvl check-sat spec.tvl.yml"
Enter
Sleep 3s

# Show a witness
Type "# Get a valid configuration witness"
Enter
Sleep 1.5s

Type "tvl witness spec.tvl.yml"
Enter
Sleep 3s

# Final pause
Sleep 3s
