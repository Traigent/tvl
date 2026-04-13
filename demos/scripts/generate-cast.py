#!/usr/bin/env python3
"""
Generate asciinema cast files from demo scripts.
This creates synthetic recordings without needing a PTY.
"""

import json
import subprocess
import time
import sys
import os

def generate_cast(script_path: str, output_path: str, title: str):
    """Generate an asciinema cast file from a script."""

    # Set up environment
    env = os.environ.copy()
    env['TERM'] = 'xterm-256color'
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(script_path)))
    env['PATH'] = os.path.join(script_dir, 'mock-cli') + ':' + env.get('PATH', '')

    # Run the script and capture output
    result = subprocess.run(
        ['bash', script_path],
        capture_output=True,
        text=True,
        env=env,
        cwd=script_dir
    )

    output = result.stdout + result.stderr

    # Create cast file
    header = {
        "version": 2,
        "width": 120,
        "height": 35,
        "timestamp": int(time.time()),
        "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"},
        "title": title
    }

    with open(output_path, 'w') as f:
        f.write(json.dumps(header) + '\n')

        # Simulate typing effect
        current_time = 0.0
        lines = output.split('\n')

        for line in lines:
            # Add the line with a delay
            if line.startswith('$') or line.startswith('#'):
                # Commands and comments - type character by character (slower for readability)
                for i, char in enumerate(line):
                    f.write(json.dumps([current_time + i * 0.05, "o", char]) + '\n')
                current_time += len(line) * 0.05 + 0.5
                f.write(json.dumps([current_time, "o", "\r\n"]) + '\n')
                current_time += 1.0  # Longer pause after command
            else:
                # Output - show with slight delay for readability
                if line:
                    f.write(json.dumps([current_time, "o", line + "\r\n"]) + '\n')
                    current_time += 0.08
                else:
                    f.write(json.dumps([current_time, "o", "\r\n"]) + '\n')
                    current_time += 0.04

        # Final pause
        f.write(json.dumps([current_time + 1.0, "o", ""]) + '\n')

    print(f"  ✓ Generated {output_path}")
    return True


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    demos_dir = os.path.dirname(script_dir)
    output_dir = os.path.join(demos_dir, 'output')

    os.makedirs(output_dir, exist_ok=True)

    demos = [
        ('demo-validate.sh', 'validate.cast', 'TVL Validation'),
        ('demo-errors.sh', 'errors.cast', 'TVL Error Diagnostics'),
        ('demo-constraints.sh', 'constraints.cast', 'TVL Constraint Checking'),
        ('demo-quickstart.sh', 'quickstart.cast', 'TVL Quick Start'),
        ('demo-optimization.sh', 'optimization.cast', 'TVL Optimization'),
    ]

    print("Generating asciinema cast files...")
    print()

    for script, output, title in demos:
        script_path = os.path.join(script_dir, script)
        output_path = os.path.join(output_dir, output)

        print(f"→ {title}")
        try:
            generate_cast(script_path, output_path, title)
        except Exception as e:
            print(f"  ✗ Error: {e}")

    print()
    print("Done! Files created in output/")
    print()
    print("To play back:")
    print("  asciinema play output/validate.cast")
    print()
    print("To convert to GIF (install agg first):")
    print("  agg output/validate.cast output/validate.gif")


if __name__ == '__main__':
    main()
