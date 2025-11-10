# Add project root to sys.path so "src" layout works when running directly
    CURRENT_FILE = Path(__file__).resolve()
    PROJECT_ROOT = CURRENT_FILE.parents[1]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from extractors.company_parser import search_companies  # type: ignore
    from extractors.utils_filters import apply_company_filters  # type: ignore
    from outputs.exporter import export_companies  # type: ignore

logger = logging.getLogger("trustpilot_scraper")

def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

def load_config(config_path: Path) -> Dict[str, Any]:
    config = load_json(config_path)
    if not isinstance(config, dict):
        raise ValueError("Configuration JSON must be an object at the top level.")
    return config

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trustpilot Company Categories Scraper"
    )
    parser.add_argument(
        "--input",
        type=str,
        default=str(
            Path(__file__).resolve().parents[1] / "data" / "input.sample.json"
        ),
        help="Path to the input JSON describing scrape parameters.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(
            Path(__file__).resolve().parents[1] / "data" / "output.sample.json"
        ),
        help="Path where scraped JSON output will be stored.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(
            Path(__file__).resolve().parent / "config" / "settings.example.json"
        ),
        help="Path to configuration JSON (headers, base URL, etc.).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    configure_logging(args.verbose)

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    config_path = Path(args.config).resolve()

    logger.info("Using input file: %s", input_path)
    logger.info("Using output file: %s", output_path)
    logger.info("Using config file: %s", config_path)

    try:
        params = load_json(input_path)
    except Exception as exc:
        logger.error("Failed to load input parameters: %s", exc)
        sys.exit(1)

    if not isinstance(params, dict):
        logger.error("Input JSON must be a single object with scrape parameters.")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except Exception as exc:
        logger.error("Failed to load configuration: %s", exc)
        sys.exit(1)

    try:
        companies = search_companies(params, config)
    except Exception as exc:
        logger.exception("Failed during company search: %s", exc)
        sys.exit(1)

    # Apply optional filters based on input parameters
    try:
        companies = apply_company_filters(companies, params)
    except Exception as exc:
        logger.exception("Failed applying filters: %s", exc)
        sys.exit(1)

    if not companies:
        logger.warning("No companies found after scraping and filtering.")

    try:
        export_companies(companies, output_path)
    except Exception as exc:
        logger.exception("Failed exporting output: %s", exc)
        sys.exit(1)

    logger.info("Scraping completed successfully. Wrote %d companies.", len(companies))

if __name__ == "__main__":
    main()