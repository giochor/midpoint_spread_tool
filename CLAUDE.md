# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This workspace is a review and analysis project for the Campaign Tactics team. It is not a standalone codebase — the relevant source code lives in GitLab and should be accessed via the GitLab MCP.

## Background

**FCAP (old platform):** Calculates reach for ATV channel only.

**Reach Optimisation (new platform):** Optimises reach and supports mixed channel allocation. FCAP was recently migrated to use Reach Optimisation.

**The problem:** With identical inputs (same data, ATV channel only), the old FCAP produces higher reach results than Reach Optimisation. The root cause is suspected to be incorrect or missing **Mid-point** and **Spread** configuration values, which must be tuned per market. These parameters govern market behaviour and are not pre-configured, requiring users to set them via trial-and-error — a process most market users cannot do correctly.

## Task (from `prompt.md`)

1. Review the Reach Optimisation implementation in GitLab.
2. Review the old FCAP implementation in GitLab.
3. Determine whether an equation or formula can be derived so markets can instantly calculate the correct Mid-point and Spread values that reproduce FCAP-equivalent reach results.
4. Propose how Mid-point and Spread can be set correctly without trial-and-error — focus on the mathematical/algorithmic solution, not UX.

## Key Concepts

- **Mid-point:** A configuration parameter in Reach Optimisation that captures market-specific reach behaviour.
- **Spread:** A configuration parameter that works alongside Mid-point to model audience reach curves.
- Both parameters are market-specific and currently must be discovered through trial-and-error by each market's users.
