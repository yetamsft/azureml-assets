# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""File for registering QnA Data as an asset."""
import argparse
from azureml.core import Run
import fsspec
import re
import time
import traceback

from azureml.rag.utils.logging import (
    get_logger,
    enable_stdout_logging,
    enable_appinsights_logging,
    track_activity,
    _logger_factory
)
from azureml.rag._asset_client.client import get_rest_client, register_new_data_asset_version

logger = get_logger('register_autoprompt_data')


def main(args, run, logger, activity_logger):
    """Extract main method to register AutoPrompt data as an AzureML UriFile asset."""
    ws = run.experiment.workspace

    logger.info(f'Checking for Autoprompt Data at: {args.storage_uri.strip("/")}')
    try:
        fsspec.open(f"{args.storage_uri}", 'r')
    except Exception as e:
        logger.error(f"Could not open Autoprompt  Data: {e}")
        activity_logger.activity_info['error'] = f'Could not open Autoprompt data output file {args.file_name}'
        raise e

    parent_run_id = run.properties.get('azureml.pipelinerunid', 'Unknown')
    client = get_rest_client(ws)
    data_version = register_new_data_asset_version(
        client,
        run,
        args.asset_name + "-best-prompts",
        args.storage_uri,
        properties={
            'azureml.autopromptDataAssetPipelineRunId': parent_run_id
        },
        output_type="UriFile")

    asset_id = re.sub(
        'azureml://locations/(.*)/workspaces/(.*)/data',
        f'azureml://subscriptions/{ws._subscription_id}/resourcegroups/'
        + f'{ws._resource_group}/providers/Microsoft.MachineLearningServices/workspaces/{ws._workspace_name}/data',
        data_version.asset_id)
    parent_run = ws.get_run(parent_run_id)
    parent_run.add_properties({"azureml.autopromptDataAssetId": asset_id})

    logger.info(f"Finished Registering MLIndex Asset '{args.asset_name}', version = {data_version.version_id}")


def main_wrapper(args, run, logger):
    """Wrap around main function."""
    with track_activity(logger, 'register_autoprompt_data') as activity_logger:
        try:
            if (args.register_output):
                main(args, run, logger, activity_logger)
            else:
                logger.info("Register output is disabled, step will passthrough without registering Autoprompt asset.")
        except Exception:
            # activity_logger doesn't log traceback
            activity_logger.error(f"register_qa_data failed with exception: {traceback.format_exc()}")
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-uri", type=str, required=True, dest='storage_uri')
    parser.add_argument("--asset-name", type=str, required=False, dest='asset_name', default='AutopromptDataset')
    parser.add_argument("--register_output", type=str, default="False")

    args = parser.parse_args()
    args.register_output = args.register_output in ["True", "true"]

    print('\n'.join(f'{k}={v}' for k, v in vars(args).items()))

    enable_stdout_logging()
    enable_appinsights_logging()

    run: Run = Run.get_context()

    try:
        main_wrapper(args, run, logger)
    finally:
        if _logger_factory.appinsights:
            _logger_factory.appinsights.flush()
            time.sleep(5)  # wait for appinsights to send telemetry
