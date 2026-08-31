- [Fix] deploy.sh: hand the marts tile functions to the pipeline role after installing them
      as superuser; a function first created by the deploy was owned by postgres and made
      the next mart refresh fail with "must be owner of function nd_survey_traces"
