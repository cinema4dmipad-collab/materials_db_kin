workflow:
  rules:
    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'
    - if: $CI_COMMIT_TAG
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH

variables:
  # Keep Poetry's in-project virtualenv between jobs so tests can run when PyPI is down.
  GIT_CLEAN_FLAGS: "-ffdx -e .venv/ -e .venv/**"

default:
  before_script:
    - poetry --version
    - poetry config --list
    - poetry config cache-dir $POETRY_CACHE_DIR
    - poetry config virtualenvs.path $POETRY_VIRTUALENVS_PATH
    - poetry config virtualenvs.in-project true

stages:
  - lint
  - test
  - build
  - docs
  - release

# Pro edition only (see generate_tomls / pyproject_pro.toml).
.variables_pro:
  variables:
    EDITION: pro

.test_template_windows:
  stage: test
  extends: .variables_pro
  script:
    - net use \\192.168.221.18\Groups $env:SMB_GROUPS_PASSWORD /user:KC\gitlab-run
    - pwsh -File scripts/ci/poetry_sync_ci.ps1
    - poetry run python generate_tomls.py -b "$EDITION"
    - Copy-Item "pyproject_${EDITION}.toml" pyproject.toml
    - Get-Content pyproject.toml
    - pwsh -File scripts/ci/poetry_sync_ci.ps1 -Lock
    - $env:QT_QPA_PLATFORM = 'offscreen'
    - $env:QT_QPA_PLATFORM
    - $TARGETDIR = '.\datas\stylesheets\fonts'
    - if (Test-Path -Path $TARGETDIR){
        $env:QT_QPA_FONTDIR = $TARGETDIR
      }
      else {
        $env:QT_QPA_FONTDIR = 'C:\Windows\Fonts'
      }
    - $env:QT_QPA_FONTDIR
    - pwsh -File scripts/ci/run_pro_tests.ps1 -DataSource '\\192.168.221.14\Groups\All\KeenetiX Test\Data' -Edition "$EDITION"
  allow_failure: false
  artifacts:
    when: always
    expire_in: 1 month
    paths:
      - ./*.log
  tags:
    - Windows (NEW)

.linux_pro_test_script: &linux_pro_test_script
  - bash scripts/ci/poetry_sync_ci.sh
  - poetry run python generate_tomls.py -b $EDITION
  - cp pyproject_$EDITION.toml pyproject.toml
  - cat pyproject.toml
  - bash scripts/ci/poetry_sync_ci.sh --lock
  - export QT_QPA_PLATFORM='offscreen'
  - echo $QT_QPA_PLATFORM
  - TARGETDIR='./datas/stylesheets/fonts'
  - |
    if [ -d "$TARGETDIR" ]; then
      export QT_QPA_FONTDIR=$TARGETDIR
    else
      export QT_QPA_FONTDIR='/usr/share/fonts'
    fi
  - echo $QT_QPA_FONTDIR
  - bash scripts/ci/run_pro_tests.sh "${KEENETIX_TEST_DATA_SOURCE:-}"

.test_template_linux:
  stage: test
  extends: .variables_pro
  before_script:
    - python --version
    - !reference [default, before_script]
  script: *linux_pro_test_script
  allow_failure: false
  artifacts:
    when: always
    expire_in: 1 month
    paths:
      - ./*.log
  tags:
    - centos9 (New)

.build_template:
  stage: build
  when: manual
  extends: .variables_pro
  script:
    - pwsh -File scripts/ci/poetry_sync_ci.ps1
    - .\build.ps1
    - net use \\192.168.221.18\Groups $env:SMB_GROUPS_PASSWORD /user:KC\gitlab-run
    - $path = '\\192.168.221.18\Groups\Программное обеспечение\RU.КНТК.122001 ПО KeenetiX\Артефакты'
    - Copy-Item .\dist\* $path -Filter *.exe
    - $limit = (Get-Date).AddDays(-30)
    - Get-ChildItem -Path $path -Recurse -Force | Where-Object {!$_.PSIsContainer -and $_.CreationTime -lt $limit} | Remove-Item -Force
    - net use \\192.168.221.18\Groups /delete
  timeout: 30 minutes
  artifacts:
    expire_in: 1 month
    paths:
      - dist/*.exe
  tags:
    - Windows (NEW)

pro_test_win:
  extends: .test_template_windows


pro_test_linux:
  extends: .test_template_linux

pro_build:
  variables:
    BUILD_MARIMO: 'false'
  extends: .build_template
  needs:
    - job: pro_test_win
      artifacts: false

pro_marimo_build:
  variables:
    BUILD_MARIMO: 'true'
  extends: .build_template
  needs:
    - job: pro_test_win
      artifacts: false

pro_cuda_build:
  variables:
    BUILD_MARIMO: 'false'
    EDITION: 'pro Cuda'
  extends: .build_template

lint:
  stage: lint
  script:
    - pwsh -File scripts/ci/poetry_sync_ci.ps1
    - poetry run ruff check --exit-zero --statistics
  rules:
    - when: always
  tags:
    - Windows (NEW)

pages:
  stage: docs
  rules:
    - if: $CI_COMMIT_BRANCH == "develop"
  script:
    - pwsh -File scripts/ci/poetry_sync_ci.ps1
    - ./docs/build/build_docs.ps1
    - Write-Host "The docs will be deployed at $CI_PAGES_URL"
  artifacts:
    paths:
      - ./public
  tags:
    - Windows (NEW)

create_release:
  stage: release
  rules:
    - if: $CI_COMMIT_BRANCH == "develop"
  script:
    - |
      $TEST_URL = "$env:CI_API_V4_URL/user"
      try {
          $user = Invoke-RestMethod -Uri $TEST_URL -Headers @{"PRIVATE-TOKEN"="$env:API_TOKEN"}
          Write-Host "Token is valid. User: $($user.username)"
      } catch {
          Write-Host "##[error]Token is invalid: $($_.Exception.Message)"
          exit 1
      }

      $PROJECT_CHECK_URL = "$env:CI_API_V4_URL/projects/$env:CI_PROJECT_ID"
      try {
          $project = Invoke-RestMethod -Uri $PROJECT_CHECK_URL -Headers @{"PRIVATE-TOKEN"="$env:API_TOKEN"}
          Write-Host "Access to project '$($project.name)' confirmed"
      } catch {
          Write-Host "##[error]No access to project: $($_.Exception.Message)"
          exit 1
      }

      $MILESTONES_URL = "$env:CI_API_V4_URL/projects/$env:CI_PROJECT_ID/milestones?state=closed"
      try {
          $milestones = Invoke-RestMethod -Uri $MILESTONES_URL -Headers @{"PRIVATE-TOKEN"="$env:API_TOKEN"}

          if (-not $milestones -or $milestones.Count -eq 0) {
              Write-Host "No closed milestones. Exit."
              exit 0
          }

          $MILESTONE_TITLE = $milestones[0].title
          Write-Host "Closed milestone found: $MILESTONE_TITLE"
      }
      catch {
          Write-Host "##[error]Error checking milestone: $_"
          exit 1
      }

      $TAGS_URL = "$env:CI_API_V4_URL/projects/$env:CI_PROJECT_ID/repository/tags"
      try {
          $tags = Invoke-RestMethod -Uri $TAGS_URL -Headers @{"PRIVATE-TOKEN"="$env:API_TOKEN"}

          if ($tags.Count -gt 0) {
              $latestTag = $tags[0].name
              Write-Host "Last tag: $latestTag"

              # Validate tag format and generate new version
              if ($latestTag -match '^v(\d+)\.(\d+)\.(\d+)$') {
                  $major = [int]$matches[1]
                  $minor = [int]$matches[2]
                  $patch = [int]$matches[3]
                  $newVersion = "v$major.$minor.$($patch+1)"
              } else {
                  Write-Host "##[error]The last tag is in an invalid format (expected vX.Y.Z)"
                  exit 1
              }
          } else {
              Write-Host "Tags not found, using default version"
              $newVersion = "v1.0.0"
          }
      }
      catch {
          Write-Host "Failed to get tags (maybe they don't exist)"
          $newVersion = "v1.0.0"
      }

      # Validate new version before creating tag
      if ($newVersion -notmatch '^v\d+\.\d+\.\d+$') {
          Write-Host "##[error]The generated version has an invalid format: $newVersion"
          exit 1
      }

      Write-Host "New version: $newVersion"

      # Create Git tag via API
      $CREATE_TAG_URL = "$env:CI_API_V4_URL/projects/$env:CI_PROJECT_ID/repository/tags?tag_name=$newVersion&ref=$env:CI_COMMIT_SHA"
      try {
          Write-Host "Create a tag $newVersion..."
          Invoke-RestMethod -Uri $CREATE_TAG_URL `
              -Method Post `
              -Headers @{"PRIVATE-TOKEN"="$env:API_TOKEN"}

          Write-Host "Tag created successfully"
      }
      catch {
          Write-Host "##[error]Error creating release:"
          Write-Host "Status Code: $($_.Exception.Response.StatusCode)"
          Write-Host "Error: $($_.ErrorDetails.Message)"
          exit 1
      }

      $RELEASE_URL = "$env:CI_API_V4_URL/projects/$env:CI_PROJECT_ID/releases"
      $BODY = @{
          tag_name = $newVersion
          name = "Release $newVersion"
          description = "Related milestone: $MILESTONE_TITLE"
          milestones = @($MILESTONE_TITLE)
      } | ConvertTo-Json -Compress

      try {
          Write-Host "Create a release for the tag $newVersion..."
          $response = Invoke-RestMethod -Uri $RELEASE_URL `
              -Method Post `
              -Headers @{
                  "PRIVATE-TOKEN" = "$env:API_TOKEN"
                  "Content-Type" = "application/json"
              } `
              -Body $BODY

          Write-Host "Release successfully created!"
          Write-Host "URL: $($response._links.self)"
      }
      catch {
          Write-Host "##[error]Error creating release:"
          Write-Host "Status Code: $($_.Exception.Response.StatusCode)"
          Write-Host "Error: $($_.ErrorDetails.Message)"
          exit 1
      }
  needs:
    - job: pro_build
    - job: pro_marimo_build
    - job: pro_cuda_build
  tags:
    - Windows (NEW)
