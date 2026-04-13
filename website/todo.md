# TVL Website TODO

## Design & Branding
- [x] Set up dark theme with blue accent colors (matching Traigent branding)
- [x] Configure Tailwind colors and typography
- [x] Add Traigent logo and branding integration
- [x] Create responsive layout with modern design

## Core Pages
- [x] Home page with hero section and key features
- [x] Specification page with language reference and schema docs
- [x] Book page with comprehensive chapters and walkthroughs
- [x] Examples page with code samples and real-world use cases

## Navigation & Layout
- [x] Create main navigation header (Home, Specification, Book, Examples)
- [x] Add footer with Traigent attribution and links
- [x] Implement responsive mobile navigation

## Content Integration
- [x] Add language reference documentation (language.md)
- [x] Add schema documentation (schema.md)
- [x] Add walkthroughs and tutorials (walkthroughs.md)
- [x] Integrate specification PDF
- [x] Add all example files (ch1-ch5 examples)
- [x] Add EBNF grammar and JSON schemas

## Features
- [x] Syntax highlighting for code examples
- [x] Downloadable specification and schemas
- [x] Interactive examples with copy functionality
- [x] Smooth scrolling and navigation
- [x] SEO optimization

## Polish
- [x] Test all pages and navigation
- [x] Verify responsive design on mobile/tablet
- [x] Check all links and downloads
- [x] Final visual polish and refinements

## New Features
- [x] Create individual chapter pages (Chapter 1-5)
- [x] Extract key content from PDF for each chapter
- [x] Make chapter cards clickable with routes
- [x] Add navigation between chapters

## Section Pages Enhancement
- [x] Make chapter sections clickable (convert to cards with links)
- [x] Create section detail pages for Chapter 2 sections
- [x] Add "First Contact" section page with ch2_hello_tvl.tvl.yml example
- [x] Add "Validation Warm-Up" section page with ch2_validate_spec.py example
- [x] Add code syntax highlighting for TVL and Python examples
- [x] Add copy-to-clipboard functionality for code blocks
- [x] Add navigation between sections within a chapter
- [x] Test all section pages and navigation

## Complete All Chapter 2 Sections
- [x] Add "A Minimal Working Spec" section page
- [x] Add "Line-by-Line Walkthrough" section page
- [x] Add "Typing Your Variables" section page
- [x] Add "Common Pitfalls" section page
- [x] Add "Objectives and Budgets" section page
- [x] Add "Promotion as a First-Class Citizen" section page
- [x] Test all 8 section pages

## Chapter 3: Constraints, Units, and Safety Nets
- [x] Review Chapter 3 content from PDF
- [x] Review ch3_constraints_units.tvl.yml and ch3_constraint_tests.py
- [x] Create section pages for all Chapter 3 sections
- [x] Add code examples with syntax highlighting
- [x] Test all Chapter 3 section pages

## Chapter 4: Patterns for Real Deployments
- [x] Review Chapter 4 content from PDF
- [x] Review ch4_environment_overlays.tvl.yml and ch4_hotfix_overlay.tvl.yml
- [x] Create section pages for all Chapter 4 sections
- [x] Add code examples with syntax highlighting
- [x] Test all Chapter 4 section pages

## Chapter 5: TVL Meets Traigent and DVL
- [x] Review Chapter 5 content from PDF
- [x] Review ch5_integration_manifest.yaml and ch5_integration_pipeline.sh
- [x] Create section pages for all Chapter 5 sections
- [x] Add code examples with syntax highlighting
- [x] Test all Chapter 5 section pages

## Fix Chapter 5 Title and Add NeMo Integration
- [x] Fix Chapter 5 title mismatch (change to "Integration Patterns")
- [x] Review NeMo Optimizer documentation
- [x] Add new section about NeMo Optimizer integration
- [x] Update chapters.json with corrected title
- [x] Test all changes

## Specification Viewer Pages
- [x] Create generic Viewer page component with syntax highlighting
- [x] Create route for JSON Schema viewer (/specification/json-schema)
- [x] Create route for EBNF Grammar viewer (/specification/ebnf-grammar)
- [x] Create route for Language Reference viewer (/specification/language-reference)
- [x] Create route for Schema Reference viewer (/specification/schema-reference)
- [x] Update Specification.tsx to link to viewer pages instead of direct downloads
- [x] Add download buttons to each viewer page
- [x] Test all viewer pages with proper syntax highlighting

## Syntax Highlighting and Missing Sections
- [x] Install and configure Prism.js or Highlight.js for syntax highlighting
- [x] Add syntax highlighting to JSON Schema viewer
- [x] Add syntax highlighting to EBNF Grammar viewer
- [x] Add syntax highlighting to Language Reference viewer (Markdown)
- [x] Add syntax highlighting to Schema Reference viewer (Markdown)
- [x] Create missing Chapter 5 sections (Automation Recipe, TVL Tooling, Looking Ahead)
- [x] Add NVIDIA NeMo Configuration Optimization section under Chapter 5
- [x] Create section page for NVIDIA NeMo Configuration Optimization
- [x] Test all syntax highlighting and new sections

## Emphasize LLM Under-Specification Message
- [x] Update home screen hero section to highlight LLM under-specification problem
- [x] Add prominent callout about LLM under-specification on home page
- [ ] Update Chapter 1 (Why TVL Exists) to emphasize under-specification message
- [ ] Create Chapter 1 section pages with content

## Add Basic Definitions Section to Chapter 2
- [x] Add "Basic Definitions" section to Chapter 2 after "First Contact"
- [x] Update chapters.json to include Basic Definitions section
- [x] Create Basic Definitions section page with tuned variable explanation
- [x] Explain temporal nature of tuned variables in LLM applications
- [x] Describe how environment changes affect tuned variables
- [x] Explain how objective changes invalidate previous assignments
- [x] Test all changes

## Fix Basic Definitions Section
- [x] Fix bold markdown rendering (** showing instead of bold text)
- [x] Add summary block at the top with key definitions
- [x] Restructure definitions to start with [**variable name**] format
- [x] Test markdown rendering in Section.tsx component

## Expand Key Concepts in Basic Definitions
- [x] Review TVL specification files to identify core concepts
- [x] Add evaluation sets/workloads to Key Concepts
- [x] Add measures/objectives to Key Concepts
- [x] Add constraints to Key Concepts
- [x] Add other essential TVL concepts (promotion policy, optimization strategy, etc.)
- [x] Keep descriptions high-level and accessible
- [x] Test updated Key Concepts section

## Improve Section Page Design and Readability
- [x] Add special handling for Key Concepts section with card-based layout
- [x] Increase spacing and improve typography for better readability
- [x] Make Key Concepts more concise and scannable
- [x] Add visual separation between concepts
- [x] Test improved design across all section pages
