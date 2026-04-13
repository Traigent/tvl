# TVL Validate Spec Demo
# Shows basic spec validation with tvl CLI

Output output/validate-spec.gif
Source tapes/_theme.tape

# Title frame
Hide
Type "clear"
Enter
Show

Sleep 1s

# Show the spec file first
Type "# Let's validate a TVL specification"
Enter
Sleep 2s

Type "cat examples/rag-support-bot.tvl.yml | head -30"
Enter
Sleep 4s

# Run validation
Type "# Now validate it with tvl"
Enter
Sleep 1s

Type "tvl validate examples/rag-support-bot.tvl.yml"
Enter
Sleep 3s

# Show success
Type "# Spec is valid! Let's check what it defines..."
Enter
Sleep 1.5s

Type "tvl info examples/rag-support-bot.tvl.yml"
Enter
Sleep 4s

# Final pause
Sleep 3s
