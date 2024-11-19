#!/usr/bin/python3

#############################################################
# Script to test whether rbac matchs the requirements.
# Ex: ./layer1/tests/rbac.py
#############################################################

import sys
import subprocess
import datetime
import time
import os
import yaml
import copy
from kubernetes import client, config
from pprint import pprint

Temporary_namespaces = {}

def main():
  apiResources = loadApiResources()
  config = load_config('rbac.yaml')
  definitions = load_config('definitions.yaml')
  start(config, definitions, apiResources)

################################################
# Start
################################################
def start(config, definitions, apiResources):
  """
    Starts the RBAC tests
  """
  print(yaml.dump(config, default_flow_style=False))

  errors = []
  for kind, items in config.get('config', {}).get('kind', {}).items():
    for impersonated, authorizations in items.items():
      print(f"===========================")
      print(f"Checking {impersonated}...")
      print(f"===========================")
      tests = []

      for scope, value in authorizations.items():
        if scope == "cluster":
          authorization = value
          tests.extend(buildCommands(definitions, apiResources, kind, impersonated, scope, authorization))
        elif scope == "namespaces":
          for namespace, authorization in value.items():
            if "*" in namespace:
              Temporary_namespaces[namespace] = create_temporary_namespace(namespace)
              tests.extend(buildCommands(definitions, apiResources, kind, impersonated, Temporary_namespaces[namespace], authorization))
            else:
              if namespace_exists(namespace):
                tests.extend(buildCommands(definitions, apiResources, kind, impersonated, namespace, authorization))
              else:
                print(f"INFO: The namespace '{namespace}' does not exist in this cluster and will be ignored.")

      # Run tests and store the errors
      errors.extend(run_tests(tests))

  # Delete created namespaces
  for _, namespace in Temporary_namespaces.items():
    print(f"Deleting temporary namespace {namespace}...")
    subprocess.run(f"kubectl delete ns {namespace}", shell=True, check=True)
    print(f"Temporary namespace {namespace} deleted.")

  # Display the list of errors
  if len(errors) == 0:
    print("\nNo error has been found.")
  else:
    print("\nList of errors:")
    for error in errors:
      print(f"{error}")
    sys.exit(1)

################################################
# Build commands
################################################
def buildCommands(definitions, apiResources, kind, impersonated, scope, authorization_value):
  """
    Returns a list of tests based on kind authorization

    Parameters:
    - definitions (map): Specifies the list of commands
    - kind (string): Specifies the kind of resource having the access. Could be `serviceaccount` or `group`
    - impersonated (string): Specifies the name of the item having the access
    - scope (string): Specifies the type of authorization. Could be `cluster` or a namespace
    - authorization_value (string): Specifies the content of the authorization

    Returns:
    array: List of tests
    [
      {'command': 'kubectl auth can-i --as=any:user --as-group=valstro:developers get namespace -A', 'expected': 'no'},
      {'command': 'kubectl auth can-i --as=any:user --as-group=valstro:developers get clusterrole -A', 'expected': 'no'}
    ]
  """
  try:
    if scope == "cluster":
      scoped_definitions = definitions[scope][authorization_value]
    else:
      scoped_definitions = definitions["namespaces"][authorization_value]
  except KeyError:
    print(f"Error: Either '{scope}' or '{authorization_value}' does not exist in definitions.")
    scoped_definitions = []

  scoped_definitions = copy.deepcopy(scoped_definitions)

  commands = []
  for command in scoped_definitions:

    # No need to test a resource if not present in the cluster
    if 'api-resource-exists' in command:
      if (command['api-resource-exists']).lower() not in apiResources:
        print(f"INFO: The Api Resource {command['api-resource-exists']} does not exist in this cluster and will be ignored.")
        continue

    # Build commands based on kind
    if kind == "serviceaccount":
      command["command"] = f'kubectl auth can-i --as={impersonated} {command["command"]}'
    elif kind == "group":
      command["command"] = f'kubectl auth can-i --as=any:user --as-group={impersonated} {command["command"]}'

    # set the namespace if namespace scoped test
    if scope != "cluster":
      command["command"] = f'{command["command"]} -n {scope}'

    commands.append(command)

  return commands


################################################
# Run Commands
################################################
def run_tests(tests):
  """
    Run a list of tests and returns a list of errors

    Parameters:
    - tests (array): The list of tests to run
    ex:
      [
        {'command': 'kubectl auth can-i --as=any:user --as-group=developers watch namespace -A', 'expected': 'yes'},
        {'command': 'kubectl auth can-i --as=any:user --as-group=developers get clusterrole -A', 'expected': 'no'}
      ]

    Returns:
    array: List of errors
  """
  errors = []
  for test in tests:
    command = test["command"]
    expected = test["expected"]
    print(f'Command:  {test["command"]}')

    # Execute the command
    process = subprocess.run(command, shell=True, stdout=subprocess.PIPE, text=True)
    result = process.stdout.strip()

    print(f'Result:   {result}')
    print(f'Expected: {expected}')

    # Display result
    if result == expected:
      print("Output:   Success")
    else:
      print("Output:   Failure")
      errors.append(f"Expected {expected}, but returns {result}. {command}")
    print("---")

  return errors

################################################
# Load config
################################################
def load_config(file_path):
  """
    Loads any yaml config
  """
  script_dir = os.path.dirname(os.path.abspath(__file__))
  file_path = os.path.join(script_dir, file_path)

  # Call the function and print the result with 2-space indentation
  try:
    with open(file_path, 'r') as file:
      return yaml.safe_load(file)
  except yaml.YAMLError as exc:
    print(f"Error parsing YAML file: {exc}")
    return None

################################################
# Check Namespace exists
################################################
def namespace_exists(namespace_name):
    try:
        config.load_kube_config()
        v1 = client.CoreV1Api()
        v1.read_namespace(namespace_name)
        return True  # Namespace exists
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return False  # Namespace does not exist
        else:
            print(f"An error occurred: {e}")
            return None
        
################################################
# Create temporary namespace
################################################
def create_temporary_namespace(prefix):
  """
    Creates a namespace with prefix
    Waits for kyverno to create the RoleBinding required to start the rbac tests.

    Parameters:

    Returns:
    string: The namespace created
  """
  if prefix in Temporary_namespaces:
    return Temporary_namespaces[prefix]

  timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
  namespace = f"{prefix.replace('*', '')}{timestamp}"

  print(f"INFO: Creating temporary namespace '{namespace}'...")

  # Create temporary namespace
  subprocess.run(f"kubectl create ns {namespace}", shell=True, check=True)

  # Wait for kyverno to create the RoleBinding 
  wait_for_kyerno_policy(namespace)

  Temporary_namespaces[prefix] = namespace
  return namespace

def wait_for_kyerno_policy(namespace):
  """
    Wait for kyverno to create the RoleBinding  (timeout: 20 iterations)
  """
  print("Waiting for kyverno to create the RoleBinding 'valstro:groups:dev-n:cluster-admin' (timeout: 20 iterations)...")
  command = f"kubectl get rolebinding valstro:groups:dev-n:cluster-admin -n {namespace}"
  for i in range(20):
    try:
      subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
      print("The rolebinding has been successfully created by kyverno...")
      break
    except subprocess.CalledProcessError:
      pass

    print("Waiting...")
    time.sleep(1)

  # Print the role binding details
  subprocess.run(command, shell=True, check=True, text=True)

################################################
# main
################################################
def loadApiResources():
  process = subprocess.run("kubectl api-resources | tail -n +2 | awk '{print $1}'", shell=True, stdout=subprocess.PIPE, text=True)
  resources = process.stdout.splitlines()
  return resources

################################################
# main
################################################
if __name__ == '__main__':
  main()