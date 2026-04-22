# Example: Build a Serena image for Terraform/OpenTofu & Ansible 

This directory demonstrates building a Serena images with the necessary dependencies for Terraform/OpenTofu and Ansible. 

The `Dockerfile` bases itself on the latest serena image, then layers the necessary dependecies on the top. 

The `compose.yaml` then builds the image and mounts the local directory as a project.