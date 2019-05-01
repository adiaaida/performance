#!/usr/bin/env python3

'''
Additional information:

This script wraps all the logic of how to build/run the .NET micro benchmarks,
acquire tools, gather data into BenchView format and upload it, archive
results, etc.

This is meant to be used on CI runs and available for local runs,
so developers can easily reproduce what runs in the lab.

Note:

The micro benchmarks themselves can be built and run using the DotNet Cli tool.
For more information refer to: benchmarking-workflow.md

../docs/benchmarking-workflow.md
  - or -
https://github.com/dotnet/performance/blob/master/docs/benchmarking-workflow.md
'''

from argparse import ArgumentParser, ArgumentTypeError
from datetime import datetime
from logging import getLogger

import os
import platform
import sys

from performance.common import validate_supported_runtime
from performance.logger import setup_loggers

import benchview
import dotnet
import micro_benchmarks


if sys.platform == 'linux' and "linux_distribution" not in dir(platform):
    MESSAGE = '''The `linux_distribution` method is missing from ''' \
        '''the `platform` module, which is used to find out information ''' \
        '''about the OS flavor/version we are using.%s''' \
        '''The Python Docs state that `platform.linux_distribution` is ''' \
        '''"Deprecated since version 3.5, will be removed in version 3.8: ''' \
        '''See alternative like the distro package.%s"''' \
        '''Most systems in the lab have Python versions 3.5 and 3.6 ''' \
        '''installed, so we are good at the moment.%s''' \
        '''If we are hitting this issue, then it might be time to look ''' \
        '''into using the `distro` module, and possibly packaing as part ''' \
        '''of the dependencies of these scripts/repo.'''
    getLogger().error(MESSAGE, os.linesep, os.linesep, os.linesep)
    exit(1)


def init_tools(
        architecture: str,
        version: str,
        target_framework_monikers: list,
        verbose: bool) -> None:
    '''
    Install tools used by this repository into the tools folder.
    This function writes a semaphore file when tools have been successfully
    installed in order to avoid reinstalling them on every rerun.
    '''
    getLogger().info('Installing tools.')
    channels = [
        micro_benchmarks.FrameworkAction.get_channel(
            target_framework_moniker)
        for target_framework_moniker in target_framework_monikers
    ]
    dotnet.install(
        architecture=architecture,
        channels=channels,
        version=version,
        verbose=verbose,
    )
    benchview.install()


def add_arguments(parser: ArgumentParser) -> ArgumentParser:
    '''Adds new arguments to the specified ArgumentParser object.'''

    if not isinstance(parser, ArgumentParser):
        raise TypeError('Invalid parser.')

    # Download DotNet Cli
    dotnet.add_arguments(parser)

    # Restore/Build/Run functionality for MicroBenchmarks.csproj
    micro_benchmarks.add_arguments(parser)

    PRODUCT_INFO = [
        'init-tools',  # Default
        'repo',
        'cli',
    ]
    parser.add_argument(
        '--cli-source-info',
        dest='cli_source_info',
        required=False,
        default=PRODUCT_INFO[0],
        choices=PRODUCT_INFO,
        help='Specifies where the product information comes from.',
    )
    parser.add_argument(
        '--cli-branch',
        dest='cli_branch',
        required=False,
        type=str,
        help='Product branch.'
    )
    parser.add_argument(
        '--cli-commit-sha',
        dest='cli_commit_sha',
        required=False,
        type=str,
        help='Product commit sha.'
    )
    parser.add_argument(
        '--cli-repository',
        dest='cli_repository',
        required=False,
        type=str,
        help='Product repository.'
    )

    def __is_valid_datetime(dt: str) -> str:
        try:
            datetime.strptime(dt, '%Y-%m-%dT%H:%M:%SZ')
            return dt
        except ValueError:
            raise ArgumentTypeError(
                'Datetime "{}" is in the wrong format.'.format(dt))

    parser.add_argument(
        '--cli-source-timestamp',
        dest='cli_source_timestamp',
        required=False,
        type=__is_valid_datetime,
        help='''Product timestamp of the soruces used to generate this build
            (date-time from RFC 3339, Section 5.6.
            "%%Y-%%m-%%dT%%H:%%M:%%SZ").'''
    )

    # Generic arguments.
    parser.add_argument(
        '-q', '--quiet',
        required=False,
        default=False,
        action='store_true',
        help='Turns off verbosity.',
    )
    parser.add_argument(
        '--build-only',
        dest='build_only',
        required=False,
        default=False,
        action='store_true',
        help='Builds the benchmarks but does not run them.',
    )
    parser.add_argument(
        '--run-only',
        dest='run_only',
        required=False,
        default=False,
        action='store_true',
        help='Attempts to run the benchmarks without building.',
    )

    # BenchView acquisition, and fuctionality
    parser = benchview.add_arguments(parser)

    return parser


def __process_arguments(args: list):
    parser = ArgumentParser(
        description='Tool to run .NET micro benchmarks',
        allow_abbrev=False,
        # epilog=os.linesep.join(__doc__.splitlines())
        epilog=__doc__,
    )
    add_arguments(parser)
    return parser.parse_args(args)


def __main(args: list) -> int:
    validate_supported_runtime()
    args = __process_arguments(args)
    verbose = not args.quiet
    setup_loggers(verbose=verbose)

    # This validation could be cleaner
    if args.generate_benchview_data and not args.benchview_submission_name:
        raise RuntimeError("""In order to generate BenchView data,
            `--benchview-submission-name` must be provided.""")

    target_framework_monikers = micro_benchmarks \
        .FrameworkAction \
        .get_target_framework_monikers(args.frameworks)
    # Acquire necessary tools (dotnet, and BenchView)
    init_tools(
        architecture=args.architecture,
        version=args.dotnet_version,
        target_framework_monikers=target_framework_monikers,
        verbose=verbose
    )

    # WORKAROUND
    # The MicroBenchmarks.csproj targets .NET Core 2.0, 2.1, 2.2 and 3.0
    # to avoid a build failure when using older frameworks (error NETSDK1045:
    # The current .NET SDK does not support targeting .NET Core $XYZ)
    # we set the TFM to what the user has provided.
    os.environ['PYTHON_SCRIPT_TARGET_FRAMEWORKS'] = ';'.join(
        target_framework_monikers
    )

    # dotnet --info
    dotnet.info(verbose=verbose)

    BENCHMARKS_CSPROJ = dotnet.CSharpProject(
        project=args.csprojfile,
        bin_directory=args.bin_directory
    )

    if not args.run_only:
        # .NET micro-benchmarks
        # Restore and build micro-benchmarks
        micro_benchmarks.build(
            BENCHMARKS_CSPROJ,
            args.configuration,
            target_framework_monikers,
            args.incremental,
            verbose
        )

    # Run micro-benchmarks
    if not args.build_only:
        for framework in args.frameworks:
            micro_benchmarks.run(
                BENCHMARKS_CSPROJ,
                args.configuration,
                framework,
                verbose,
                args
            )

        benchview.run_scripts(args, verbose, BENCHMARKS_CSPROJ)
        # TODO: Archive artifacts.


if __name__ == "__main__":
    __main(sys.argv[1:])
