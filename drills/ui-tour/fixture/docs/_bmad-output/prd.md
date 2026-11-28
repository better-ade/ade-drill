# PRD: team invoices

## Goals

- A team sees what it owes, and why, before the month ends.
- Finance exports every invoice of a month in one file.

## Flow

```mermaid
graph LR
  Seats[Seats used] --> Invoice[Monthly invoice]
  Invoice --> Export[CSV export]
```
