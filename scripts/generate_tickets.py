"""Generate the fictional support tickets used by the offline demo.

Deterministic (seeded). Writes data/demo/tickets.csv and tickets_planted.json (which issue each
ticket was generated from, used to check the clustering finds the recurring problems). All
people, files, and part numbers are invented.

Usage: python scripts/generate_tickets.py
"""

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "demo"
rng = random.Random(20261020)
START, END = datetime(2025, 10, 1, 8), datetime(2026, 10, 1, 8)
CUTOVER = datetime(2026, 6, 1)  # planted: BOM transfer failures rise after the SAP cutover
UNITS = ["Electrical Products", "Aerospace Systems", "eMobility", "Industrial Controls"]
PEOPLE = ["A. Novak", "B. Osei", "C. Lindqvist", "D. Mehta", "E. Duarte", "F. Haddad",
          "G. Brennan", "H. Sato", "I. Moreau", "J. Adeyemi", "K. Petrov", "L. Fischer",
          "M. Garcia", "N. Kowalski", "O. Bakr", "P. Singh"]


def pn() -> str:
    return f"{rng.choice([100, 210, 330, 450])}-00{rng.randrange(4100, 8999)}"


def fname() -> str:
    return f"{rng.choice(['bracket', 'housing', 'cover', 'busbar', 'panel', 'mount'])}_" \
           f"{rng.randrange(100, 999)}.{rng.choice(['prt', 'asm', 'drw'])}"


# issue: (weight, KB article or "" for a knowledge gap, short descriptions, details, resolution)
ISSUES = {
    "locked file": (0.14, "KB-101", [
        "CAD file locked by another user", "Cannot check out {f}, checked out by someone else",
        "File locked in vault", "Need {f} unlocked, owner left the company",
        "Vault says file is checked out by {p}"], [
        "I need to edit {f} but the vault shows it checked out by {p}.",
        "{p} has had {f} checked out for two weeks and is on leave.",
        "Cannot save my changes to {f}; vault says it is locked."],
        "Vault admin forced undo check-out after manager approval."),
    "export folder access": (0.11, "", [
        "Access to export-controlled drawings folder",
        "Need access to ITAR folder for program drawings",
        "Request access to controlled project folder", "Cannot open export-controlled folder",
        "Access denied on controlled drawings"], [
        "I joined the program team and need the controlled drawings folder for {f}.",
        "Folder request in the portal was rejected; it says controlled folders are not covered.",
        "New on the aerospace program, need to see the controlled models."],
        "Routed to Trade Compliance for screening, then access granted by vault admin."),
    "bom not in sap": (0.09, "KB-301", [
        "Released BOM not in SAP", "BOM transfer to SAP failed for {pn}",
        "Plant cannot see new BOM", "SAP missing BOM released yesterday",
        "Integration error on BOM {pn}"], [
        "Released {pn} two days ago and the plant still does not see it in SAP.",
        "Transfer status shows Failed for {pn}; plant {plant} is waiting.",
        "BOM released but SAP still shows the old revision for {pn}."],
        "Integration team corrected the mapping and retried the transfer."),
    "eco status": (0.09, "KB-202", [
        "Where is my ECO", "ECO stuck in approval", "ECO waiting at change board for weeks",
        "Who has my ECO", "ECO not moving"], [
        "My ECO has been at change board for three weeks and nobody can tell me why.",
        "Can someone check who is holding my ECO? It has not moved since last month.",
        "ECO for {pn} is stuck; plant needs it next week."],
        "Showed the user the Route tab; change coordinator sent a reminder."),
    "license": (0.08, "KB-503", [
        "No PLM license available", "Cannot get a license", "License error when starting PLM",
        "All licenses in use"], [
        "Getting 'no license available' every morning since Monday.",
        "Cannot start the PLM client, license error.",
        "Our team keeps running out of licenses after lunch."],
        "License released by timeout; advised manager to request seats if it recurs."),
    "eco returned": (0.07, "KB-203", [
        "ECO returned, how do I resubmit", "ECO sent back to me", "Reviewer rejected my ECO",
        "What do I do with a returned ECO"], [
        "My ECO came back with a comment about affected parts; how do I fix and resubmit?",
        "ECO for {pn} was returned; do I need to create a new one?",
        "Reviewer sent my ECO back, not sure what to change."],
        "Explained the resubmit step; user resubmitted the same ECO."),
    "role access": (0.07, "KB-501", [
        "Access denied in PLM", "Need PLM engineer role", "Cannot create parts, no permission",
        "Request change coordinator role"], [
        "I can sign in but get access denied when I open parts.",
        "New hire needs the engineer role to create parts.",
        "Need change coordinator role to route ECOs for my team."],
        "Role request approved and granted."),
    "missing references": (0.06, "KB-701", [
        "Assembly opens with missing references", "Missing parts when opening {f}",
        "References not found in assembly"], [
        "Opening {f} shows 14 missing references.", "Assembly loads with empty components.",
        "Missing references after a colleague renamed parts."],
        "Resolved references from vault and checked in."),
    "duplicate part": (0.06, "KB-401", [
        "Cannot find existing part, created a new one", "Is there already a part for this",
        "Part search does not find {pn}", "Search returns nothing for hex bolt M8"], [
        "Search did not find the bracket so I drew it again; data steward says it is a duplicate.",
        "Is there an existing part for a stainless M8 bolt? Search returns hundreds.",
        "Cannot find {pn} by its description."],
        "Showed classification search; existing part found."),
    "viewer old revision": (0.05, "", [
        "Viewer shows old revision", "Released drawing still old in viewer",
        "Wrong revision in viewer after release", "Viewer not updated after ECO release"], [
        "ECO released this morning but the viewer still shows revision B of {pn}.",
        "Plant sees the old drawing in the viewer after release.",
        "Viewer cache seems stale for {pn}."],
        "Cleared viewer cache on the server; revision showed after refresh."),
    "checkin timeout": (0.05, "KB-102", [
        "Check-in times out over VPN", "Large assembly check-in fails",
        "Vault check-in timeout"], [
        "Checking in a 3,000 part assembly from home fails after 20 minutes.",
        "Check-in of {f} times out on VPN.", "Vault client hangs on check-in."],
        "Set remote site cache; check-in succeeded."),
    "cad crash": (0.04, "KB-702", [
        "CAD crashes opening drawing", "Client crash on large drawing", "CAD freezes"], [
        "CAD client crashes every time I open {f}.", "Large drawing freezes the client.",
        "Crash when switching to shaded view."],
        "Enabled large assembly mode and updated the graphics driver."),
    "where-used export": (0.04, "", [
        "Where-used export times out", "Cannot export where-used to Excel",
        "Where-used report fails for common part"], [
        "Exporting where-used for {pn} to Excel spins and fails.",
        "Where-used report times out for fasteners used in many assemblies.",
        "Need the where-used list for an ECO but the export fails."],
        "Ran the report for the user from the database."),
    "classification": (0.03, "KB-402", [
        "Release blocked by classification", "Cannot release part, required attribute missing",
        "Classification required error"], [
        "Release of {pn} is blocked: required attribute missing.",
        "Which class do I pick for a cable gland?",
        "Part will not release, says classification incomplete."],
        "Helped user pick the class and fill required attributes."),
}
OTHER = (0.02, ["Monitor flickers", "Keyboard not working", "Teams meeting audio issue",
                "Printer offline on floor 2", "Laptop battery swelling", "VPN slow at home"])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tickets, truth = [], {}
    names = list(ISSUES) + ["other"]
    t, n = START, 0
    while t < END:
        n += 1
        weights = [ISSUES[k][0] * (3.0 if k == "bom not in sap" and t >= CUTOVER else 1.0)
                   for k in ISSUES] + [OTHER[0]]
        issue = rng.choices(names, weights)[0]
        unit, who = rng.choice(UNITS), rng.choice(PEOPLE)
        fill = {"f": fname(), "p": rng.choice(PEOPLE), "pn": pn(),
                "plant": rng.choice(["1010", "1020", "2030", "3100"])}
        if issue == "other":
            short, desc, kb = rng.choice(OTHER[1]), "See title.", ""
            note = "Fixed by desktop support."
            hours = rng.uniform(1, 30)
        else:
            _, kb_id, shorts, details, note = ISSUES[issue]
            short = rng.choice(shorts).format(**fill)
            desc = rng.choice(details).format(**fill)
            kb = kb_id if kb_id and rng.random() < 0.55 else ""
            hours = rng.lognormvariate(3.2 if kb_id else 3.9, 0.7)  # gaps take longer
        key = f"INC{n:06d}"
        tickets.append({"ticket": key, "created": t.isoformat(timespec="minutes"),
                        "business_unit": unit, "requester": who, "short_description": short,
                        "description": desc, "kb_article": kb,
                        "resolved": (t + timedelta(hours=hours)).isoformat(timespec="minutes"),
                        "resolution": note})
        truth[key] = issue
        t += timedelta(hours=rng.expovariate(1 / 4.4))
    with (OUT / "tickets.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(tickets[0]))
        w.writeheader()
        w.writerows(tickets)
    (OUT / "tickets_planted.json").write_text(json.dumps({
        "_note": "Issue each ticket was generated from (scripts/generate_tickets.py).",
        "as_of": END.isoformat(timespec="minutes"), "cutover": CUTOVER.isoformat()[:10],
        "gaps": sorted(k for k, v in ISSUES.items() if not v[1]),
        "rising": "bom not in sap", "issue": truth}, indent=0) + "\n")
    counts = {k: sum(v == k for v in truth.values()) for k in names}
    print(f"{len(tickets)} tickets: " + ", ".join(f"{k} {c}" for k, c in counts.items()))


if __name__ == "__main__":
    main()
