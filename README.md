# k8s-rbac-tests

RBAC (Role-Based Access Control) in Kubernetes is a security mechanism, granting or restricting access based on user roles and permissions.  
It ensures a fine-grained approach to safeguard Kubernetes clusters, preventing unauthorized actions.  

By testing RBAC policies, you can ensure that only authorized users or service accounts have access to specific resources, reducing the risk of unauthorized access or actions.  

Please read the Medium article for more details about the tests:  
https://pierreraffa.medium.com/how-to-test-kubernetes-rbac-with-python-b126f37c09bf

### RBAC for namespace-scoped Custom Resources 

This script performs more than just building/testing the kubectl commands. It is also possible to test the access to a CR when the Custom Resource Definition (CRD) exists.  
The script lists all available resources by running kubectl api-resources and ignores the tests for any resources that are not present in the cluster by using the field `api-resource-exists`.  

```yaml
...
namespace:  
  ro:
    - command: get keycloakclients
      expected: "yes"
      api-resource-exist: keycloakclients
    - command: create keycloakclients
      expected: "no"
      api-resource-exists: keycloakclients
    - command: delete keycloakclients
      expected: "no"
      api-resource-exists: keycloakclients
    - command: get keycloakrealms
      expected: "yes"
      api-resource-exists: keycloakrealms
    - command: create keycloakrealms
      expected: "no"
      api-resource-exists: keycloakrealms
    - command: delete keycloakrealms
      expected: "no"
      api-resource-exists: keycloakrealms
    - command: get fixtenants
      expected: "yes"
      api-resource-exists: fixtenants
    - command: create fixtenants
      expected: "no"
      api-resource-exists: fixtenants
    - command: delete fixtenants
      expected: "no"
      api-resource-exists: fixtenants
...
```

### Runng Tests

```bash
python3.11 rbac.py
```

Output:
```
===========================
Checking system:serviceaccount:kyverno:kyverno...
===========================
Command:  kubectl auth can-i --as=system:serviceaccount:kyverno:kyverno '*' '*'
Result:   yes
Expected: yes
Output:   Success

===========================
Checking valstro:developers...
===========================
Command:  kubectl auth can-i --as=any:user --as-group=valstro:developers '*' '*'
Result:   no
Expected: no
Output:   Success
---
Command:  kubectl auth can-i --as=any:user --as-group=valstro:developers create namespace -A
Result:   yes
Expected: yes
Output:   Success
---
Command:  kubectl auth can-i --as=any:user --as-group=valstro:developers get namespace -A
Result:   yes
Expected: yes
Output:   Success

etc...

No error has been found.
```