"""CLI. Failures are one JSON object on stderr."""

from __future__ import annotations

import argparse
import json
import sys
import traceback

from mymlfw import __version__
from mymlfw.errors import MymlfwError


def _file_sha256(path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mymlfw", exit_on_error=False)
    parser.add_argument("--debug", action="store_true")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("version", exit_on_error=False)

    profile = sub.add_parser("profile-data", exit_on_error=False)
    profile.add_argument("--dir", required=True)
    profile.add_argument("--out", default=None)
    profile.add_argument(
        "--recommend",
        action="store_true",
        help="Recommendations are always written. This flag is accepted for callers that pass it.",
    )

    probe = sub.add_parser("probe", exit_on_error=False)
    probe_sub = probe.add_subparsers(dest="probe_cmd")
    register = probe_sub.add_parser("register", exit_on_error=False)
    register.add_argument("--ledger", required=True)
    register.add_argument("--experiment-id", required=True)
    register.add_argument("--baseline-id", default="")
    register.add_argument("--variable", required=True)
    register.add_argument("--change-count", type=int, default=1)
    register.add_argument("--band-low", type=float, required=True)
    register.add_argument("--band-high", type=float, required=True)
    register.add_argument("--note", default="")
    update_cv = probe_sub.add_parser("update-cv", exit_on_error=False)
    update_cv.add_argument("--ledger", required=True)
    update_cv.add_argument("--experiment-id", required=True)
    update_cv.add_argument("--cv-mean", type=float, required=True)
    update_cv.add_argument("--cv-std", type=float, default=None)
    score = probe_sub.add_parser("score", exit_on_error=False)
    score.add_argument("--ledger", required=True)
    score.add_argument("--experiment-id", required=True)
    score.add_argument("--public-score", type=float, required=True)
    verdict = probe_sub.add_parser("verdict", exit_on_error=False)
    verdict.add_argument("--ledger", required=True)
    verdict.add_argument("--experiment-id", required=True)
    verdict.add_argument("--verdict", required=True)
    verdict.add_argument("--note", default=None)
    sha = probe_sub.add_parser("sha", exit_on_error=False)
    sha.add_argument("--ledger", required=True)
    sha.add_argument("--experiment-id", required=True)
    sha.add_argument("--artifact", required=True)

    blend = sub.add_parser("blend", exit_on_error=False)
    blend_sub = blend.add_subparsers(dest="blend_cmd")
    optimize = blend_sub.add_parser("optimize", exit_on_error=False)
    optimize.add_argument("--oof", action="append", required=True)
    optimize.add_argument("--labels", required=True)
    optimize.add_argument("--manifest", required=True)
    optimize.add_argument("--l2", type=float, default=0.05)
    optimize.add_argument("--metric", choices=("log_loss", "accuracy", "balanced_accuracy"), default="log_loss")
    reorder = blend_sub.add_parser("reorder-classes", exit_on_error=False)
    reorder.add_argument("--target", required=True)
    reorder.add_argument("--source", required=True)
    reorder.add_argument("--out", required=True)
    diversity = blend_sub.add_parser("diversity", exit_on_error=False)
    diversity.add_argument("--oof", action="append", required=True)
    diversity.add_argument("--cv", action="append", required=True, type=float)
    diversity.add_argument("--strict", action="store_true")

    diagnose = sub.add_parser("diagnose-oof", exit_on_error=False)
    diagnose.add_argument("--oof", required=True)
    diagnose.add_argument("--train", required=True)
    diagnose.add_argument("--out", required=True)

    shift = sub.add_parser("check-shift", exit_on_error=False)
    shift.add_argument("--train", required=True)
    shift.add_argument("--test", required=True)
    shift.add_argument("--numeric", required=True)

    simulate = sub.add_parser("simulate-test", exit_on_error=False)
    simulate.add_argument("--train", required=True)
    simulate.add_argument("--rows", type=int, default=25000)
    simulate.add_argument("--out", required=True)
    simulate.add_argument("--sample-seconds", type=float, default=1.0)

    pack = sub.add_parser("pack-deps", exit_on_error=False)
    pack.add_argument("--requirements", required=True)
    pack.add_argument("--out", required=True)
    pack.add_argument("--dry-run", action="store_true")

    pre = sub.add_parser("preflight", exit_on_error=False)
    pre.add_argument("--ledger", required=True)
    pre.add_argument("--experiment-id", required=True)
    pre.add_argument("--artifact", required=True)
    pre.add_argument("--gate", required=True)
    pre.add_argument("--leak", required=True)
    pre.add_argument("--runtime", required=True)
    pre.add_argument("--kernel", required=True)
    pre.add_argument("--scale-report", default=None)
    pre.add_argument("--require-scale-report", action="store_true")
    pre.add_argument("--previous-hashes", default=None)

    submit = sub.add_parser("submit", exit_on_error=False)
    submit_sub = submit.add_subparsers(dest="submit_cmd")
    check = submit_sub.add_parser("check", exit_on_error=False)
    check.add_argument("--kind", choices=("id_label", "ranked"), required=True)
    check.add_argument("--file", required=True)
    check.add_argument("--label-col", default="label")
    check.add_argument("--classes", default="")
    check.add_argument("--max-k", type=int, default=25)

    kernel = sub.add_parser("kernel", exit_on_error=False)
    kernel_sub = kernel.add_subparsers(dest="kernel_cmd")
    build = kernel_sub.add_parser("build", exit_on_error=False)
    build.add_argument("--src", required=True)
    build.add_argument("--out", required=True)
    build.add_argument("--payload", action="append", required=True)

    cloud = sub.add_parser("cloud", exit_on_error=False)
    cloud_sub = cloud.add_subparsers(dest="cloud_cmd")
    launch = cloud_sub.add_parser("launch", exit_on_error=False)
    launch.add_argument("--project", required=True)
    launch.add_argument("--role", required=True)
    launch.add_argument("--gpu", required=True)
    launch.add_argument("--command", dest="shell_command", required=True)
    launch.add_argument("--idle-kill", type=int, required=True)
    launch.add_argument("--max-runtime", type=int, required=True)
    launch.add_argument("--ledger", required=True)
    launch.add_argument("--experiment-id", required=True)
    launch.add_argument("--baseline-id", required=True)
    launch.add_argument("--variable", required=True)
    launch.add_argument("--band-low", type=float, required=True)
    launch.add_argument("--band-high", type=float, required=True)
    launch.add_argument("--note", default="")
    launch.add_argument("--out", required=True)

    train = sub.add_parser("train", exit_on_error=False)
    train_sub = train.add_subparsers(dest="train_cmd")
    lora = train_sub.add_parser("lora", exit_on_error=False)
    lora.add_argument("--dry-run", action="store_true")
    lora.add_argument("--smoke", action="store_true")
    lora.add_argument("--config", default=None)
    lora.add_argument("--train", default=None)
    lora.add_argument("--ledger", default=None)
    lora.add_argument("--experiment-id", default=None)
    lora.add_argument("--baseline-id", default=None)
    lora.add_argument("--variable", default=None)
    lora.add_argument("--band-low", type=float, default=None)
    lora.add_argument("--band-high", type=float, default=None)
    lora.add_argument("--note", default="")
    lora.add_argument("--soft-targets", default=None)
    lora.add_argument("--kl-alpha", type=float, default=0.5)
    lora.add_argument("--out", default=None)
    soup = train_sub.add_parser("soup", exit_on_error=False)
    soup.add_argument("--adapter", action="append", required=True)
    soup.add_argument("--weight", action="append", required=True, type=float)
    soup.add_argument("--out", required=True)
    grpo = train_sub.add_parser("grpo", exit_on_error=False)
    grpo.add_argument("--groups", required=True)

    contest = sub.add_parser("new-contest", exit_on_error=False)
    contest.add_argument("name")
    contest.add_argument("--dest", required=True)

    recipes = sub.add_parser("recipes", exit_on_error=False)
    recipes.add_argument("--match", default="")
    recipes.add_argument("--show", default="")

    archive = sub.add_parser("archive-contest", exit_on_error=False)
    archive.add_argument("--ledger", required=True)
    archive.add_argument("--playbook", required=True)
    archive.add_argument("--recipe", default=None)

    remember = sub.add_parser("remember", exit_on_error=False)
    remember.add_argument("--tag", required=True)
    remember.add_argument("--rule", required=True)
    remember.add_argument("--evidence", default="")
    remember.add_argument("--notes", default=None)
    remember.add_argument("--db", default=None)

    episode = sub.add_parser("episode", exit_on_error=False)
    episode_sub = episode.add_subparsers(dest="episode_command", required=True)
    episode_add = episode_sub.add_parser("add", exit_on_error=False)
    episode_add.add_argument("--contest", required=True)
    episode_add.add_argument("--task", required=True)
    episode_add.add_argument("--actions", required=True)
    episode_add.add_argument("--outcome", required=True)
    episode_add.add_argument("--lesson", required=True)
    episode_add.add_argument("--evidence", default="")
    episode_add.add_argument("--tag", default="")
    episode_add.add_argument("--supersedes", default=None)
    episode_add.add_argument("--db", default=None)
    episode_recall = episode_sub.add_parser("recall", exit_on_error=False)
    episode_recall.add_argument("--task", required=True)
    episode_recall.add_argument("--data-dir", default=None)
    episode_recall.add_argument("--db", default=None)

    ingest_cmd = sub.add_parser("ingest", exit_on_error=False)
    ingest_cmd.add_argument("--path", default=None)
    ingest_cmd.add_argument("--mode", choices=("docs", "repo", "auto"), default="auto")
    ingest_cmd.add_argument("--tag", default="")
    ingest_cmd.add_argument("--db", default=None)
    ingest_cmd.add_argument("--sync", action="store_true")

    search_cmd = sub.add_parser("search", exit_on_error=False)
    search_cmd.add_argument("text", nargs="?", default=None)
    search_cmd.add_argument("--query", default=None)
    search_cmd.add_argument("--type", dest="chunk_type", default="code_pattern")
    search_cmd.add_argument("--db", default=None)

    advise_cmd = sub.add_parser("advise", exit_on_error=False)
    advise_cmd.add_argument("--dir", required=True)
    advise_cmd.add_argument("--db", default=None)
    advise_cmd.add_argument("--task", default="next experiment")
    advise_cmd.add_argument("--clean", action="store_true")
    advise_cmd.add_argument("--id", default=None)

    analyze_cmd = sub.add_parser("analyze", exit_on_error=False)
    analyze_cmd.add_argument("--dir", required=True)
    analyze_cmd.add_argument("--db", default=None)
    analyze_cmd.add_argument("--task", default="")
    analyze_cmd.add_argument("--out", default=None)

    promote = sub.add_parser("promote-plugin", exit_on_error=False)
    promote.add_argument("plugin")
    promote.add_argument("--category", required=True)
    promote.add_argument("--dest", default=None)
    promote.add_argument("--tests-dest", default=None)

    sub.add_parser("sync-docs", exit_on_error=False)

    project_cmd = sub.add_parser("project", exit_on_error=False)
    project_sub = project_cmd.add_subparsers(dest="project_cmd")
    project_dash = project_sub.add_parser("dashboard", exit_on_error=False)
    project_dash.add_argument("--project", required=True)
    project_dash.add_argument(
        "--api",
        default=None,
        help="API base URL (default MYMLFW_API or http://127.0.0.1:8000)",
    )
    project_dash.add_argument(
        "--token",
        default=None,
        help="Bearer token (default MYMLFW_TOKEN)",
    )

    runner = sub.add_parser("runner", exit_on_error=False)
    runner_sub = runner.add_subparsers(dest="runner_cmd")
    runner_start = runner_sub.add_parser("start", exit_on_error=False)
    runner_start.add_argument(
        "--once",
        action="store_true",
        help="Single heartbeat + claim then exit (stub).",
    )
    runner_start.add_argument("--poll-seconds", type=float, default=5.0)
    runner_sub.add_parser("status", exit_on_error=False)

    return parser


def _dispatch(args) -> int:
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "profile-data":
        from mymlfw.campaign.profile import profile_dir

        path = profile_dir(args.dir, args.out)
        print(path)
        return 0
    if args.command == "probe" and args.probe_cmd == "register":
        from mymlfw.campaign.ledger import register_probe

        row = register_probe(
            args.ledger,
            experiment_id=args.experiment_id,
            baseline_id=args.baseline_id,
            variable=args.variable,
            change_count=args.change_count,
            expected_band_low=args.band_low,
            expected_band_high=args.band_high,
            note=args.note,
        )
        print(json.dumps({"experiment_id": row["experiment_id"], "verdict": row["verdict"]}))
        return 0
    if args.command == "probe" and args.probe_cmd == "update-cv":
        from mymlfw.campaign.ledger import update_cv

        row = update_cv(args.ledger, args.experiment_id, args.cv_mean, args.cv_std)
        print(json.dumps({"experiment_id": row["experiment_id"], "cv_mean": row["cv_mean"], "cv_delta": row["cv_delta"]}))
        return 0
    if args.command == "probe" and args.probe_cmd == "score":
        from mymlfw.campaign.ledger import record_public_score

        row = record_public_score(args.ledger, args.experiment_id, args.public_score)
        print(json.dumps({"experiment_id": row["experiment_id"], "verdict": row["verdict"], "cv_lb_gap": row["cv_lb_gap"]}))
        return 0
    if args.command == "probe" and args.probe_cmd == "verdict":
        from mymlfw.campaign.ledger import set_verdict

        row = set_verdict(args.ledger, args.experiment_id, args.verdict, args.note)
        print(json.dumps({"experiment_id": row["experiment_id"], "verdict": row["verdict"]}))
        return 0
    if args.command == "probe" and args.probe_cmd == "sha":
        from mymlfw.campaign.ledger import set_artifact_sha

        row = set_artifact_sha(args.ledger, args.experiment_id, _file_sha256(args.artifact))
        print(json.dumps({"experiment_id": row["experiment_id"], "artifact_sha256": row["artifact_sha256"]}))
        return 0
    if args.command == "blend" and args.blend_cmd == "optimize":
        import pandas as pd

        from mymlfw.blend import load_npz, optimize_weights
        from mymlfw.blend.optimize import score_bundle
        from mymlfw.submit.manifest import write_manifest

        bundles = [load_npz(path) for path in args.oof]
        labels = pd.read_csv(args.labels)
        column = "label" if "label" in labels.columns else labels.columns[-1]
        y = labels[column].to_numpy()
        weights = optimize_weights(
            bundles,
            y,
            lambda truth, bundle: score_bundle(truth, bundle, args.metric),
            l2=args.l2,
        )
        write_manifest(args.manifest, weights, "log_linear", artifact_sha256="")
        print(args.manifest)
        return 0
    if args.command == "blend" and args.blend_cmd == "reorder-classes":
        from mymlfw.blend.reorder import reorder_classes

        reorder_classes(args.target, args.source, args.out)
        print(args.out)
        return 0
    if args.command == "blend" and args.blend_cmd == "diversity":
        from mymlfw.blend import diversity_matrix, load_npz

        if len(args.oof) != len(args.cv):
            raise MymlfwError(
                "DIVERSITY_COUNT",
                "Pass one --cv value for each --oof file.",
                oof=len(args.oof),
                cv=len(args.cv),
            )
        report = diversity_matrix([load_npz(path) for path in args.oof], args.cv, strict=args.strict)
        warnings = report["warnings"]
        print(json.dumps({"warnings": warnings}))
        return 0
    if args.command == "diagnose-oof":
        from mymlfw.blend import diagnose_oof

        diagnose_oof(args.oof, args.train, args.out)
        print(args.out)
        return 0
    if args.command == "check-shift":
        from mymlfw.blend import check_shift

        numeric = [part.strip() for part in args.numeric.split(",") if part.strip()]
        result = check_shift(args.train, args.test, numeric)
        print(json.dumps(result))
        return 0
    if args.command == "simulate-test":
        from mymlfw.kernel import simulate_test

        def hook(n_sample, frame):
            return args.sample_seconds, 1.0

        report = simulate_test(args.train, args.rows, hook, args.out)
        print(json.dumps({"projected_seconds": report["projected_seconds"]}))
        return 0
    if args.command == "pack-deps":
        from mymlfw.kernel import pack_deps

        plan = pack_deps(args.requirements, args.out, dry_run=True if args.dry_run or True else False)
        if not args.dry_run:
            plan = pack_deps(args.requirements, args.out, dry_run=False)
        print(plan["cmd"])
        print(plan["snippet"])
        return 0
    if args.command == "preflight":
        from mymlfw.submit import preflight

        result = preflight(
            ledger=args.ledger,
            experiment_id=args.experiment_id,
            artifact=args.artifact,
            gate=args.gate,
            leak=args.leak,
            runtime=args.runtime,
            kernel=args.kernel,
            scale_report=args.scale_report,
            require_scale_report=args.require_scale_report,
            previous_hashes=args.previous_hashes,
        )
        print(json.dumps(result))
        return 0
    if args.command == "submit" and args.submit_cmd == "check":
        import pandas as pd

        from mymlfw.submit import check_id_label, check_ranked_topk

        frame = pd.read_csv(args.file)
        if args.kind == "id_label":
            classes = [part.strip() for part in args.classes.split(",") if part.strip()]
            check_id_label(frame, args.label_col, classes)
        else:
            check_ranked_topk(frame, max_k=args.max_k)
        print(json.dumps({"ok": True, "rows": int(len(frame))}))
        return 0
    if args.command == "kernel" and args.kernel_cmd == "build":
        from mymlfw.kernel import build_notebook

        manifest = build_notebook(args.src, args.out, args.payload)
        print(json.dumps({"notebook_sha256": manifest["notebook_sha256"]}))
        return 0
    if args.command == "cloud" and args.cloud_cmd == "launch":
        from pathlib import Path

        from mymlfw.cloud import JobSpec, render_launch

        spec = JobSpec(
            project=args.project,
            role=args.role,
            gpu=args.gpu,
            command=args.shell_command,
            idle_kill_minutes=args.idle_kill,
            max_runtime_minutes=args.max_runtime,
            experiment_id=args.experiment_id,
            baseline_id=args.baseline_id,
            variable=args.variable,
            expected_band_low=args.band_low,
            expected_band_high=args.band_high,
            note=args.note,
        )
        script = render_launch(spec, args.ledger)
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(script)
        destination.chmod(0o755)
        print(destination)
        return 0
    if args.command == "train" and args.train_cmd == "lora":
        report = {}
        if args.dry_run:
            missing = [
                name
                for name in ("train", "ledger", "experiment_id", "baseline_id", "variable", "band_low", "band_high")
                if getattr(args, name) in (None, "")
            ]
            if missing:
                raise MymlfwError("USAGE", "Pass the ledger and data flags with --dry-run.", missing=missing)
            from mymlfw.train.lora import lora_dry_run

            report = lora_dry_run(
                args.train,
                args.ledger,
                experiment_id=args.experiment_id,
                baseline_id=args.baseline_id,
                variable=args.variable,
                expected_band_low=args.band_low,
                expected_band_high=args.band_high,
                note=args.note,
                soft_targets=args.soft_targets,
                kl_alpha=args.kl_alpha,
                out_dir=args.out,
                config=args.config,
            )
        if args.smoke:
            try:
                from mymlfw.train.lora import smoke_backward

                report["smoke"] = smoke_backward()
            except ImportError as exc:
                raise MymlfwError(
                    "TRAIN_EXTRA",
                    "Install the train extra: pip install -e '.[train]'.",
                    note=str(exc),
                ) from exc
        if not args.dry_run and not args.smoke:
            raise MymlfwError(
                "DRY_RUN_REQUIRED",
                "Pass --dry-run or --smoke. Weight downloads are outside the test suite.",
            )
        print(json.dumps(report))
        return 0
    if args.command == "train" and args.train_cmd == "soup":
        from mymlfw.train.soup import soup_adapters

        path = soup_adapters(args.adapter, args.weight, args.out)
        print(path)
        return 0
    if args.command == "train" and args.train_cmd == "grpo":
        from pathlib import Path

        from mymlfw.train.grpo import score_groups

        rows = json.loads(Path(args.groups).read_text())
        print(json.dumps(score_groups(rows)))
        return 0
    if args.command == "new-contest":
        from mymlfw.scaffold import new_contest

        path = new_contest(args.name, args.dest)
        print(path)
        return 0
    if args.command == "recipes":
        from mymlfw.scaffold import list_recipes, show_recipe

        if args.show:
            text = show_recipe(args.show)
            print(text, end="" if text.endswith("\n") else "\n")
            return 0
        for card in list_recipes(args.match):
            print(f"{card['id']}: {card['summary']}")
        return 0
    if args.command == "archive-contest":
        from mymlfw.scaffold import archive_contest

        path = archive_contest(args.ledger, args.playbook, recipe=args.recipe)
        print(path)
        return 0
    if args.command == "remember":
        from mymlfw.scaffold import remember

        result = remember(args.tag, args.rule, args.evidence, notes=args.notes, db=args.db)
        if result["status"] == "duplicate":
            print("duplicate")
        else:
            print(result["path"])
        return 0
    if args.command == "episode":
        from mymlfw.rag.episodes import add_episode, recall_text

        if args.episode_command == "add":
            result = add_episode(
                args.contest,
                args.task,
                args.actions,
                args.outcome,
                args.lesson,
                evidence=args.evidence,
                tags=args.tag,
                supersedes=args.supersedes,
                db=args.db,
            )
            print("duplicate" if result["status"] == "duplicate" else result["id"])
            return 0
        print(recall_text(args.task, db=args.db, data_dir=args.data_dir))
        return 0
    if args.command == "ingest":
        from mymlfw.rag.ingest import ingest

        print(json.dumps(ingest(args.path, mode=args.mode, tags=args.tag, db=args.db, sync=args.sync)))
        return 0
    if args.command == "search":
        from mymlfw.rag.ingest import search

        query = args.query or args.text
        if not query:
            raise MymlfwError("USAGE", "Pass a search query.")
        print(json.dumps(search(query, chunk_type=args.chunk_type, db=args.db)))
        return 0
    if args.command == "advise":
        from mymlfw.rag.advise import advise, clean

        if args.clean:
            if not args.id:
                raise MymlfwError("ADVICE_ID", "Pass --id with the short id from the advise branch.")
            print(json.dumps(clean(args.dir, args.id)))
            return 0
        print(json.dumps(advise(args.dir, db=args.db, task=args.task)))
        return 0
    if args.command == "analyze":
        from mymlfw.rag.analyze import analyze

        print(json.dumps(analyze(args.dir, db=args.db, task=args.task, out=args.out)))
        return 0
    if args.command == "promote-plugin":
        from mymlfw.scaffold import promote_plugin

        path = promote_plugin(args.plugin, args.category, dest=args.dest, tests_dest=args.tests_dest)
        print(path)
        return 0
    if args.command == "sync-docs":
        from mymlfw.scaffold import sync_llms_index

        path = sync_llms_index()
        print(path)
        return 0
    if args.command == "project" and args.project_cmd == "dashboard":
        import os
        import urllib.error
        import urllib.request

        base = (
            args.api
            or os.environ.get("MYMLFW_API")
            or "http://127.0.0.1:8000"
        ).rstrip("/")
        token = args.token or os.environ.get("MYMLFW_TOKEN") or ""
        url = f"{base}/v1/projects/{args.project}/dashboard"
        req = urllib.request.Request(url, method="GET")
        req.add_header("X-Mymlfw-Client-Version", __version__)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise MymlfwError(
                "DASHBOARD_HTTP",
                "Pass --token / MYMLFW_TOKEN and a valid --project.",
                status=exc.code,
                note=body,
            ) from exc
        except urllib.error.URLError as exc:
            raise MymlfwError(
                "DASHBOARD_UNREACHABLE",
                "Start the API (make dev) or pass --api.",
                note=str(exc.reason),
            ) from exc
        return 0
    if args.command == "runner":
        from mymlfw.runner.cli import print_json, runner_start, runner_status

        if args.runner_cmd == "status":
            print_json(runner_status())
            return 0
        if args.runner_cmd == "start":
            print_json(runner_start(once=args.once, poll_seconds=args.poll_seconds))
            return 0
        raise MymlfwError("USAGE", "Use: mymlfw runner start|status")
    raise MymlfwError("UNKNOWN_COMMAND", "Run python -m mymlfw version.")


def main(argv=None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        return _dispatch(args)
    except MymlfwError as exc:
        payload = exc.to_dict()
        if getattr(locals().get("args", None), "debug", False) or (argv and "--debug" in argv) or "--debug" in sys.argv:
            payload["traceback"] = traceback.format_exc()
        print(json.dumps(payload), file=sys.stderr)
        return 1
    except argparse.ArgumentError as exc:
        payload = {
            "error_code": "USAGE",
            "suggested_fix": "Run python -m mymlfw version.",
            "note": str(exc),
        }
        if "--debug" in sys.argv or (argv and "--debug" in argv):
            payload["traceback"] = traceback.format_exc()
        print(json.dumps(payload), file=sys.stderr)
        return 1
    except Exception as exc:
        payload = {
            "error_code": "UNHANDLED",
            "suggested_fix": "Re-run with --debug.",
            "note": str(exc),
        }
        if "--debug" in sys.argv or (argv and "--debug" in argv):
            payload["traceback"] = traceback.format_exc()
        print(json.dumps(payload), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
