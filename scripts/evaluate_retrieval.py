"""Evaluate seeded retrieval against ticket ground truth without calling generation."""
import argparse
import json
import sys

ROOT = __import__('pathlib').Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai import AIService
from config import settings
from engine import rank_candidates
from storage import MongoStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=0, help='Evaluate at most this many incoming cases (default: all).')
    parser.add_argument('--k', type=int, default=5, help='Recall cutoff (default: 5).')
    args = parser.parse_args()
    if args.k < 1 or args.limit < 0:
        parser.error('--k must be positive and --limit cannot be negative.')

    store = MongoStore(settings)
    try:
        store.initialize()
        cases = [item for item in store.records('investigation') if item.get('ground_truth') and item.get('data_origin') == 'Synthetic demo']
        cases.sort(key=lambda item: item.get('ticket_id', item['id']))
        if args.limit:
            cases = cases[:args.limit]
        if not cases:
            raise SystemExit('No seeded incoming test cases found. Run scripts/seed_tickets.py first.')
        ai = AIService(settings)
        rows = []
        for ticket in cases:
            truth = ticket['ground_truth']
            expected = set(truth.get('correct_precedent_ids', []))
            if not expected:
                continue
            ranked, _ = rank_candidates(ticket, store, ai)
            ordered_ids = list(dict.fromkeys(row['source']['id'] for row in ranked))
            hits = expected.intersection(ordered_ids[:args.k])
            first_rank = next((index for index, source_id in enumerate(ordered_ids, 1) if source_id in expected), None)
            rows.append(dict(ticket_id=ticket.get('ticket_id', ticket['id']),
                recall_at_k=len(hits) / len(expected), reciprocal_rank=1 / first_rank if first_rank else 0,
                expected=sorted(expected), retrieved_top_k=ordered_ids[:args.k], hit=bool(hits)))
        if not rows:
            raise SystemExit('No ground-truth cases with correct precedent IDs were found.')
        output = dict(data_origin='Synthetic demo; not production performance', cases=len(rows),
            k=args.k, recall_at_k=round(sum(row['recall_at_k'] for row in rows) / len(rows), 4),
            mrr=round(sum(row['reciprocal_rank'] for row in rows) / len(rows), 4),
            hit_rate_at_k=round(sum(row['hit'] for row in rows) / len(rows), 4),
            cases_detail=rows)
        print(json.dumps(output, indent=2, ensure_ascii=False))
    finally:
        store.close()


if __name__ == '__main__':
    main()
