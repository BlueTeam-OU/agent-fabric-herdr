use crate::api::schema::IntegrationTarget;

pub(super) fn run_integration_command(args: &[String]) -> std::io::Result<i32> {
    let Some(subcommand) = args.first().map(|arg| arg.as_str()) else {
        print_integration_help();
        return Ok(2);
    };

    match subcommand {
        "install" => integration_install(&args[1..]),
        "uninstall" => integration_uninstall(&args[1..]),
        "status" => integration_status(&args[1..]),
        "help" | "--help" | "-h" => {
            print_integration_help();
            Ok(0)
        }
        _ => {
            print_integration_help();
            Ok(2)
        }
    }
}

fn integration_status(args: &[String]) -> std::io::Result<i32> {
    let outdated_only = match args {
        [] => false,
        [flag] if flag == "--outdated-only" => true,
        _ => {
            eprintln!("usage: agent-fabric-fleetdeck integration status [--outdated-only]");
            return Ok(2);
        }
    };

    if outdated_only {
        crate::integration::print_outdated_update_notice();
        return Ok(0);
    }

    for status in crate::integration::installed_integration_statuses() {
        let target = crate::integration::integration_target_label(status.target);
        let state = describe_integration_state(
            status.state,
            status.installed_version,
            status.expected_version,
        );
        println!("{target}: {state} ({})", status.path.display());
    }

    if let Some(status) = crate::integration::experimental_letta_integration_status() {
        let state = describe_integration_state(
            status.state,
            status.installed_version,
            status.expected_version,
        );
        println!(
            "{} (experimental): {state} ({})",
            status.label,
            status.path.display()
        );
    }

    Ok(0)
}

fn describe_integration_state(
    state: crate::integration::IntegrationStatusKind,
    installed_version: Option<u32>,
    expected_version: u32,
) -> String {
    let version = match installed_version {
        Some(version) => format!("v{version}"),
        None => "legacy".to_string(),
    };
    match state {
        crate::integration::IntegrationStatusKind::NotInstalled => "not installed".to_string(),
        crate::integration::IntegrationStatusKind::Current => format!("current ({version})"),
        crate::integration::IntegrationStatusKind::Outdated
            if installed_version.is_some_and(|installed| installed >= expected_version) =>
        {
            format!("needs repair ({version})")
        }
        crate::integration::IntegrationStatusKind::Outdated => {
            format!("outdated ({version} < v{expected_version})")
        }
    }
}

fn integration_install(args: &[String]) -> std::io::Result<i32> {
    let Some(target) = parse_integration_target(args, "install")? else {
        return Ok(2);
    };

    let installed = match target {
        IntegrationCommandTarget::Builtin(target) => crate::integration::install_target(target),
        IntegrationCommandTarget::Letta => crate::integration::install_experimental_letta(),
    };
    match installed {
        Ok(messages) => {
            print_integration_messages(messages);
            Ok(0)
        }
        Err(err) => {
            eprintln!("{err}");
            Ok(1)
        }
    }
}

fn integration_uninstall(args: &[String]) -> std::io::Result<i32> {
    let Some(target) = parse_integration_target(args, "uninstall")? else {
        return Ok(2);
    };

    let removed = match target {
        IntegrationCommandTarget::Builtin(target) => crate::integration::uninstall_target(target),
        IntegrationCommandTarget::Letta => crate::integration::uninstall_experimental_letta(),
    };
    match removed {
        Ok(messages) => {
            print_integration_messages(messages);
            Ok(0)
        }
        Err(err) => {
            eprintln!("{err}");
            Ok(1)
        }
    }
}

fn print_integration_messages(messages: Vec<String>) {
    for message in messages {
        println!("{message}");
    }
}

/// Integration target accepted by the CLI. Letta is deliberately kept out of
/// the frozen client endpoint `IntegrationTarget` enum and is handled as an
/// experimental CLI-only target until the agent registry replaces it.
enum IntegrationCommandTarget {
    Builtin(IntegrationTarget),
    Letta,
}

fn parse_integration_target(
    args: &[String],
    action: &str,
) -> std::io::Result<Option<IntegrationCommandTarget>> {
    let Some(target) = args.first().map(|arg| arg.as_str()) else {
        eprintln!(
            "usage: agent-fabric-fleetdeck integration {action} <pi|omp|claude|codex|copilot|devin|droid|kimi|opencode|kilo|hermes|qodercli|qwen|letta|cursor|mastracode|grok>"
        );
        return Ok(None);
    };
    if args.len() != 1 {
        eprintln!(
            "usage: agent-fabric-fleetdeck integration {action} <pi|omp|claude|codex|copilot|devin|droid|kimi|opencode|kilo|hermes|qodercli|qwen|letta|cursor|mastracode|grok>"
        );
        return Ok(None);
    }

    let parsed = match target {
        "pi" => IntegrationCommandTarget::Builtin(IntegrationTarget::Pi),
        "omp" => IntegrationCommandTarget::Builtin(IntegrationTarget::Omp),
        "claude" => IntegrationCommandTarget::Builtin(IntegrationTarget::Claude),
        "codex" => IntegrationCommandTarget::Builtin(IntegrationTarget::Codex),
        "copilot" => IntegrationCommandTarget::Builtin(IntegrationTarget::Copilot),
        "devin" => IntegrationCommandTarget::Builtin(IntegrationTarget::Devin),
        "droid" => IntegrationCommandTarget::Builtin(IntegrationTarget::Droid),
        "kimi" => IntegrationCommandTarget::Builtin(IntegrationTarget::Kimi),
        "opencode" => IntegrationCommandTarget::Builtin(IntegrationTarget::Opencode),
        "kilo" => IntegrationCommandTarget::Builtin(IntegrationTarget::Kilo),
        "hermes" => IntegrationCommandTarget::Builtin(IntegrationTarget::Hermes),
        "qodercli" => IntegrationCommandTarget::Builtin(IntegrationTarget::Qodercli),
        "qwen" => IntegrationCommandTarget::Builtin(IntegrationTarget::Qwen),
        "letta" => IntegrationCommandTarget::Letta,
        "cursor" => IntegrationCommandTarget::Builtin(IntegrationTarget::Cursor),
        "mastracode" => IntegrationCommandTarget::Builtin(IntegrationTarget::Mastracode),
        "antigravity-cli" | "antigravity_cli" => {
            IntegrationCommandTarget::Builtin(IntegrationTarget::AntigravityCli)
        }
        "grok" => IntegrationCommandTarget::Builtin(IntegrationTarget::Grok),
        _ => {
            eprintln!("unknown integration target: {target}");
            eprintln!(
                "currently supported: pi, omp, claude, codex, copilot, devin, droid, kimi, opencode, kilo, hermes, qodercli, qwen, letta, cursor, mastracode, antigravity-cli, grok"
            );
            return Ok(None);
        }
    };

    Ok(Some(parsed))
}

fn print_integration_help() {
    eprintln!("agent-fabric-fleetdeck integration commands:");
    eprintln!("  agent-fabric-fleetdeck integration install pi");
    eprintln!("  agent-fabric-fleetdeck integration install omp");
    eprintln!("  agent-fabric-fleetdeck integration install claude");
    eprintln!("  agent-fabric-fleetdeck integration install codex");
    eprintln!("  agent-fabric-fleetdeck integration install copilot");
    eprintln!("  agent-fabric-fleetdeck integration install devin");
    eprintln!("  agent-fabric-fleetdeck integration install droid");
    eprintln!("  agent-fabric-fleetdeck integration install kimi");
    eprintln!("  agent-fabric-fleetdeck integration install opencode");
    eprintln!("  agent-fabric-fleetdeck integration install kilo");
    eprintln!("  agent-fabric-fleetdeck integration install hermes");
    eprintln!("  agent-fabric-fleetdeck integration install qodercli");
    eprintln!("  agent-fabric-fleetdeck integration install qwen");
    eprintln!("  agent-fabric-fleetdeck integration install letta");
    eprintln!("  agent-fabric-fleetdeck integration install cursor");
    eprintln!("  agent-fabric-fleetdeck integration install mastracode");
    eprintln!("  agent-fabric-fleetdeck integration install antigravity-cli");
    eprintln!("  agent-fabric-fleetdeck integration install grok");
    eprintln!("  agent-fabric-fleetdeck integration uninstall pi");
    eprintln!("  agent-fabric-fleetdeck integration uninstall omp");
    eprintln!("  agent-fabric-fleetdeck integration uninstall claude");
    eprintln!("  agent-fabric-fleetdeck integration uninstall codex");
    eprintln!("  agent-fabric-fleetdeck integration uninstall copilot");
    eprintln!("  agent-fabric-fleetdeck integration uninstall devin");
    eprintln!("  agent-fabric-fleetdeck integration uninstall droid");
    eprintln!("  agent-fabric-fleetdeck integration uninstall kimi");
    eprintln!("  agent-fabric-fleetdeck integration uninstall opencode");
    eprintln!("  agent-fabric-fleetdeck integration uninstall kilo");
    eprintln!("  agent-fabric-fleetdeck integration uninstall hermes");
    eprintln!("  agent-fabric-fleetdeck integration uninstall qodercli");
    eprintln!("  agent-fabric-fleetdeck integration uninstall qwen");
    eprintln!("  agent-fabric-fleetdeck integration uninstall letta");
    eprintln!("  agent-fabric-fleetdeck integration uninstall cursor");
    eprintln!("  agent-fabric-fleetdeck integration uninstall mastracode");
    eprintln!("  agent-fabric-fleetdeck integration uninstall antigravity-cli");
    eprintln!("  agent-fabric-fleetdeck integration uninstall grok");
    eprintln!("  agent-fabric-fleetdeck integration status [--outdated-only]");
}
