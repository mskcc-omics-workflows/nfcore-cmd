## {{ your_module_name }}

#### Description:

{{ your_module_description }}

#### Usage:

Inputs:

- input_file_1
- input_file_2

Outputs:

- output_file_1
- output_file_2

Testing/Example:

```
nextflow run tests/main.nf -profile docker
```

#### Reference
#### Building docker container and making a new module release

1. Navigate to the appropriate download page. {{ your_module_name }}: download the rpm of the desired version with `curl` or `wget` or any other format of the tool.
2. For RPM package, use `rpm2cpio *.rpm | cpio -i --make-directories` to unpack. Place the executable located in `<unpack_dir>/usr/bin/<tool>` in the same folder where the Dockerfile lies.
3. Create and test the container:

   ```bash
   docker build . -t mpathdms/<tool>:<VERSION>
   ```

4. Access rights are needed to push the container to the Dockerhub mpathdms organization, please ask a core team member to do so.

   ```bash
   docker push mpathdms/<tool>:<VERSION>
   ```
