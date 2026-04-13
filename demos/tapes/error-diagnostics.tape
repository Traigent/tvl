# TVL Error Diagnostics Demo
# Shows helpful error messages and diagnostics

Output output/error-diagnostics.gif
Source tapes/_theme.tape

Hide
Type "clear"
Enter
Show

Sleep 500ms

# Introduction
Type "# TVL Error Diagnostics"
Enter
Sleep 1s

# Create a spec with errors
Type "cat > broken.tvl.yml << 'EOF'"
Enter
Type "tvl:"
Enter
Type "  module: demo.errors"
Enter
Type "tvl_version: '0.9'"
Enter
Enter
Type "tvars:"
Enter
Type "  - name: model"
Enter
Type "    type: enum[str]"
Enter
Type "    domain: []  # Empty domain!"
Enter
Type "  - name: temp"
Enter
Type "    type: float"
Enter
Type "    domain: { range: [0.0, 1.0] }"
Enter
Enter
Type "constraints:"
Enter
Type "  structural:"
Enter
Type "    - expr: 'unknown_var = true'  # Undeclared!"
Enter
Type "    - expr: 'temp = 0.5'  # Float equality"
Enter
Type "EOF"
Enter
Sleep 1s

# Run validation
Type "# Run validation to see diagnostics..."
Enter
Sleep 500ms

Type "tvl validate broken.tvl.yml"
Enter
Sleep 3s

# Show the error codes
Type "# Each error has a code for easy lookup"
Enter
Sleep 500ms

Type "tvl explain E1002"
Enter
Sleep 2s

# Clean up
Type "rm broken.tvl.yml"
Enter

Sleep 2s
