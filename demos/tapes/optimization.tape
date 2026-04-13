# TVL Optimization Demo
# Shows the value proposition: from vague requirements to precise specs + optimization

Output output/optimization.gif
Source tapes/_theme.tape

# Clear screen
Hide
Type "clear"
Enter
Show

Sleep 1s

# Hook: The problem
Type "# The Problem: Vague AI Requirements"
Enter
Sleep 2s

Type 'echo "PM: Build me a customer support agent"'
Enter
Sleep 1.5s

Type 'echo "PM: Can you make it cheaper?"'
Enter
Sleep 1.5s

Type 'echo "PM: It is not accurate enough..."'
Enter
Sleep 2s

Type ""
Enter

# The solution
Type "# The Solution: Precise, Optimizable Specifications"
Enter
Sleep 2s

# Show a compact spec
Type "cat << 'EOF'"
Enter
Type "# support-bot.tvl.yml"
Enter
Type "objectives:"
Enter
Type "  - name: accuracy"
Enter
Type "    metric_ref: metrics.accuracy.v1"
Enter
Type "    direction: maximize"
Enter
Type "    target: '>= 0.85'        # 85% accuracy minimum"
Enter
Type "  - name: latency_ms"
Enter
Type "    metric_ref: metrics.latency_ms.v1"
Enter
Type "    direction: minimize"
Enter
Type "    target: '<= 200'         # Under 200ms"
Enter
Type "  - name: cost_per_query"
Enter
Type "    metric_ref: metrics.cost_per_query.v1"
Enter
Type "    direction: minimize"
Enter
Type "    target: '<= 0.01'        # Under 1 cent"
Enter
Type "EOF"
Enter
Sleep 3s

Type ""
Enter

# Run optimization
Type "# Let the optimizer find the best configuration"
Enter
Sleep 1.5s

Type "tvo run support-bot.tvl.yml --max-trials 50"
Enter
Sleep 6s

# Final message
Type ""
Enter
Type "# Precise specs + automatic optimization = better AI systems"
Enter
Sleep 3s
