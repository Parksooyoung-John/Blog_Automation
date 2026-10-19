---
name: web-design-guidelines
description: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
metadata:
  author: vercel
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines

Review files for compliance with Web Interface Guidelines.

## How It Works

1. Read the local `rules.md`
2. Read the specified files (or prompt user for files/pattern)
3. Check against all rules in the rules.md
4. Output findings in the terse `file:line` format

## Guidelines Source

Pinned local copy (fetched 2026-10-19 from vercel-labs/web-interface-guidelines `command.md`, MIT): `rules.md` in this folder. Read it with Read; do NOT fetch remote rules at review time. Refresh manually and review the diff.

## Usage

When a user provides a file or pattern argument:
1. Read local `rules.md`
2. Read the specified files
3. Apply all rules from the rules.md
4. Output findings using the format specified in the guidelines

If no files specified, ask the user which files to review.
