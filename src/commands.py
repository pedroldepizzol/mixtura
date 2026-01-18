import argparse
from typing import Dict, List
from utils import log_task, log_info, log_success, log_warn, log_error, Style
from manager import ModuleManager

def _get_manager_or_warn(name: str):
    mgr = ModuleManager.get_instance().get_manager(name)
    if not mgr:
        log_warn(f"Package manager '{name}' is not available or not found.")
    return mgr

def cmd_add(args: argparse.Namespace) -> None:
    manager = ModuleManager.get_instance()
    
    # We need to manually parse args to distinguish "naked" packages
    # resolve_packages forces a default provider which we want to avoid if possible for 'add'
    # Actually, resolve_packages logic: 
    # if '#' not in arg: defaults to 'nixpkgs' (or whatever default)
    
    # New logic: iterate over args. 
    # If arg has '#', use it.
    # If not, search ALL providers.
    
    packages_to_install: Dict[str, List[str]] = {}
    
    for arg in args.packages:
        if '#' in arg:
            # Explicit provider
            provider, pkg = arg.split('#', 1)
            if provider not in packages_to_install:
                packages_to_install[provider] = []
            packages_to_install[provider].append(pkg)
        else:
            # Ambiguous package - Search Mode
            log_task(f"Searching for '{Style.BOLD}{arg}{Style.RESET}' across all providers...")
            results = manager.search_all(arg)
            
            if not results:
                log_warn(f"No packages found for '{arg}'.")
                continue
            
            # Interactive Selection
            print(f"\n{Style.BOLD}Found {len(results)} matches for '{arg}':{Style.RESET}")
            
            # Pagination/Limit could be good but let's list all for now (capped by provider implementation usually)
            for i, res in enumerate(results):
                idx = i + 1
                name = res.get('name', 'unknown')
                prov = res.get('provider', 'unknown')
                ver = res.get('version', '')
                desc = res.get('description', '')[:60] # truncate desc
                if len(res.get('description', '')) > 60: desc += "..."
                
                print(f" {Style.SUCCESS}{idx}.{Style.RESET} {Style.BOLD}{name}{Style.RESET} {Style.DIM}({prov} {ver}){Style.RESET}")
                if desc:
                    print(f"    {desc}")
            
            print()
            try:
                choice = input(f"{Style.INFO}Select a package to add (1-{len(results)}) or 's' to skip: {Style.RESET}")
                if choice.lower() == 's' or choice.lower() == 'q':
                    print("Skipping...")
                    continue
                
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(results):
                    selected = results[choice_idx]
                    prov = selected['provider']
                    
                    # We need the ID for installation
                    # Nix: we used attribute path as ID
                    # Flatpak: ID is app ID
                    # Homebrew: ID is name
                    pkg_id = selected.get('id') or selected.get('name')
                    
                    if prov not in packages_to_install:
                        packages_to_install[prov] = []
                    
                    packages_to_install[prov].append(pkg_id)
                    log_info(f"Selected {selected['name']} from {prov}")
                else:
                    log_error("Invalid selection.")
            except ValueError:
                log_error("Invalid input.")

    # Proceed with installation
    if not packages_to_install:
        log_warn("No packages selected for installation.")
        return

    print()
    for provider_name, packages in packages_to_install.items():
        mgr = _get_manager_or_warn(provider_name)
        if mgr and mgr.is_available():
            log_task(f"Installing {len(packages)} packages via {mgr.name}...")
            mgr.install(packages)
        else:
            if mgr:
                log_error(f"Provider '{mgr.name}' is not available.")
            else:
                 log_error(f"Provider '{provider_name}' unknown.")

    log_success("Installation process finished.")

def cmd_remove(args: argparse.Namespace) -> None:
    manager = ModuleManager.get_instance()
    grouped_packages = manager.resolve_packages(args.packages)

    if not grouped_packages:
        log_warn("No packages specified.")
        return

    for provider_name, packages in grouped_packages.items():
        mgr = _get_manager_or_warn(provider_name)
        if mgr:
             log_task(f"Removing {len(packages)} packages via {mgr.name}...")
             mgr.uninstall(packages)

    log_success("Removal process finished.")

def cmd_upgrade(args: argparse.Namespace) -> None:
    manager = ModuleManager.get_instance()
    
    # 1. Upgrade ALL
    if not args.packages:
        log_task("Upgrading all available providers...")
        for mgr in manager.get_all_managers():
            if mgr.is_available():
                log_info(f"Upgrading {mgr.name}...")
                mgr.upgrade(None) # None = all
        log_success("Upgrade complete.")
        return

    # 2. Upgrade specific provider (e.g. 'nixpkgs')
    # Or specific packages
    packages_map: Dict[str, List[str]] = {}
    providers_full = []
    
    # Reuse simple logic or custom parsing?
    # Let's use simple manual parsing as resolve_packages forces default.
    
    for arg in args.packages:
        # Check if arg is a provider name
        if manager.get_manager(arg):
            providers_full.append(arg)
            continue
            
        if '#' in arg:
            prov, pkg = arg.split('#', 1)
            if prov not in packages_map: packages_map[prov] = []
            packages_map[prov].append(pkg)
        else:
            # Default fallback for upgrade? 
            # Assume 'nixpkgs' as default for upgrade context if not specified? 
            # Or should we warn?
            # Existing behavior was defaulting to nixpkgs.
            prov = 'nixpkgs'
            if prov not in packages_map: packages_map[prov] = []
            packages_map[prov].append(arg)

    # Execute full upgrades
    for prov in providers_full:
        mgr = _get_manager_or_warn(prov)
        if mgr and mgr.is_available():
            log_task(f"Upgrading all packages in {prov}...")
            mgr.upgrade(None)

    # Execute package specific upgrades
    for prov, pkgs in packages_map.items():
        mgr = _get_manager_or_warn(prov)
        if mgr and mgr.is_available():
            log_task(f"Upgrading specific packages in {prov}...")
            mgr.upgrade(pkgs)

    if not packages_map and not providers_full:
        log_warn("No packages or providers specified for upgrade.")
    else:
        log_success("Upgrade process finished.")

def cmd_list(args: argparse.Namespace) -> None:
    manager = ModuleManager.get_instance()
    
    target = args.type
    managers_to_list = []
    
    if target:
        m = manager.get_manager(target)
        if m: 
            managers_to_list.append(m)
        else:
            log_warn(f"Unknown provider '{target}'")
            return
    else:
        managers_to_list = manager.get_all_managers()

    if not managers_to_list:
        log_warn("No package managers found.")
        return

    first = True
    for mgr in managers_to_list:
        if not mgr.is_available():
            continue

        if not first:
            print()
        first = False
            
        log_task(f"Fetching packages from {mgr.name}...")
        pkgs = mgr.list_packages()
        
        if pkgs:
            print(f"{Style.BOLD}{Style.INFO}:: {mgr.name} ({len(pkgs)}){Style.RESET}")
            for pkg in pkgs:
                # support various keys
                name = pkg.get('name', 'unknown')
                extra = pkg.get('version') or pkg.get('id') or pkg.get('origin') or ''
                print(f"  {Style.SUCCESS}•{Style.RESET} {Style.BOLD}{name}{Style.RESET} {Style.DIM}({extra}){Style.RESET}")
        else:
             print(f"{Style.DIM}No packages found in {mgr.name}{Style.RESET}")

def cmd_search(args: argparse.Namespace) -> None:
    manager = ModuleManager.get_instance()
    # If args.query is a list, we handle each.
    # Note: argparse definition for 'search' usually takes 'query' as nargs='+'
    
    for q in args.query:
        if '#' in q:
             # Provider specific search
             prov, term = q.split('#', 1)
             mgr = _get_manager_or_warn(prov)
             if mgr and mgr.is_available():
                 results = mgr.search(term)
                 if results:
                     print(f"{Style.BOLD}Results for '{term}' in {prov}:{Style.RESET}")
                     for res in results:
                         print(f"  • {res.get('name')} ({res.get('version')}) - {res.get('description')}")
                 else:
                     log_warn(f"No results for '{term}' in {prov}")
        else:
             # Search all
             log_task(f"Searching for '{q}'...")
             results = manager.search_all(q)
             if results:
                 print(f"{Style.BOLD}Results for '{q}':{Style.RESET}")
                 for res in results:
                      prov = res.get('provider')
                      print(f"  [{prov}] {res.get('name')} ({res.get('version')}) - {res.get('description')}")
             else:
                 log_warn(f"No results for '{q}'")
