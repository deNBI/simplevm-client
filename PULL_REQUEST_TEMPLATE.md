Try to fulfill the following points before the Pull Request is merged:

**Codebase and Testing**
- [ ] Code changes are covered with [unit tests](https://github.com/deNBI/guidelines/blob/master/unittests.md)
- [ ] For changes in DB: migrations are made and pushed to the branch
- [ ] The dev branch is merged into the current branch
- [ ] If a linting PR exists, it must be merged before this PR is allowed to be merged.

**Documentation**
- [ ] Check if anything in the Readme must be adjusted (development-, production-, setup).
- [ ] Check if any section in the wiki (https://simplevm.denbi.de/wiki/) should be adjusted.
- [ ] If code is unreadable and not well commented: Open commenting issue with tag "important"

**Security**
- [ ] For any new features or security changes, check against the [OWASP guidelines](https://github.com/deNBI/guidelines/blob/master/owasp_top10.md) for possible vulnerabilities
- [ ] For any updates in packages and requirements: Check if the patches still work

For releases only:
- [ ] If the review of this PR is approved and the PR is followed by a release then the .env file
  in the cloud-portal repo should also be updated.
- [ ] If you are making a release then please sum up the changes since the last release on the release page using the [clog](https://github.com/clog-tool/clog-cli) tool with `clog -F`

