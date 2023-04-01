To build the test database, use the following command:

```
dbbuilder -b . -c . -o -t
```

To render the CV, use the following command (after building the database):

```
render_cv -c .
```

The cv will be rendered to `output/cv.pdf`

We use the `-t` flag to limit the number of publications which will speed up database creation.
